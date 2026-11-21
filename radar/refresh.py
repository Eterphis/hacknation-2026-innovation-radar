"""Odświeżenie danych ze źródeł: Interreg 2021–2027 i NCBR (wyszukiwarka sukcesów).

    python -X utf8 -m radar.refresh                       # oba źródła, tylko to, co się zmieniło
    python -X utf8 -m radar.refresh --sources interreg    # jedno źródło
    python -X utf8 -m radar.refresh --dry-run             # sprawdź, co by zrobił, nic nie zapisuj
    python -X utf8 -m radar.refresh --force               # pobierz i przebuduj wszystko od nowa
    python -X utf8 -m radar.refresh --offline             # przebuduj z zapisanych plików, bez sieci

Mechanizmy:
- blokada (`data/.refresh.lock`): dwa odświeżenia naraz się nie nadpiszą; blokada martwego
  procesu albo starsza niż 6 h jest przejmowana;
- Interreg: plik XLSX jest pobierany tylko wtedy, gdy na stronie jest link do innego pliku
  niż zapisany albo zapisanego pliku brakuje / ma inną sumę SHA-256; pobrany plik musi być
  poprawnym XLSX (archiwum ZIP), inaczej zostaje poprzedni;
- NCBR: strona listy jest pobierana ponownie dopiero, gdy zapisana jest starsza niż `--max-age`
  godzin; strony szczegółów już pobrane są brane z dysku, pobierane są tylko nowe karty;
- przebudowa wyniku jest pomijana, gdy dane wejściowe (SHA-256) się nie zmieniły i wynik istnieje;
- poprzedni wynik zostaje jako `*.prev.jsonl`; gdy liczba rekordów spadnie o ponad połowę,
  skrypt ostrzega i kończy się kodem 1 (prawdopodobna zmiana formatu źródła);
- błąd jednego źródła nie zatrzymuje drugiego; stan i historia w `data/refresh_state.json`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .http import FetchError, fetch, fetch_bytes
from .sources import interreg, ncbr

DATA = Path("data")
STATE_FILE = DATA / "refresh_state.json"
LOCK_FILE = DATA / ".refresh.lock"
LOCK_STALE_SECONDS = 6 * 3600
HISTORY_LIMIT = 50
DROP_WARN_RATIO = 0.5


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("rb") as fh:
        return sum(1 for line in fh if line.strip())


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text("utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(path)


# --- lock ----------------------------------------------------------------------
def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    except SystemError:  # Windows: os.kill(pid, 0) may raise on some builds
        return True
    return True


class Lock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.held = False

    def __enter__(self) -> "Lock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                info = read_json(self.path)
                age = time.time() - self.path.stat().st_mtime
                if age < LOCK_STALE_SECONDS and _pid_alive(int(info.get("pid", 0))):
                    raise SystemExit(f"odświeżanie już trwa (pid {info.get('pid')}, od {info.get('started')}); "
                                     f"jeśli to nieprawda, usuń {self.path}")
                log(f"przejmuję porzuconą blokadę {self.path}")
                self.path.unlink(missing_ok=True)
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"pid": os.getpid(), "started": now_iso()}, fh)
            self.held = True
            return self
        raise SystemExit(f"nie udało się założyć blokady {self.path}")

    def __exit__(self, *exc) -> None:
        if self.held:
            self.path.unlink(missing_ok=True)


# --- output handling -----------------------------------------------------------
def rebuild(out: Path, run) -> dict:
    """Keep the previous output as *.prev.jsonl, run the connector, compare counts."""
    before = count_lines(out)
    prev = out.with_name(out.stem + ".prev" + out.suffix)
    if out.exists():
        shutil.copy2(out, prev)
    rc = run()
    if rc != 0:
        raise RuntimeError(f"konektor zakończył się kodem {rc}")
    after = count_lines(out)
    result = {"records_before": before, "records": after, "output_sha256": sha256_file(out)}
    if before and after < before * DROP_WARN_RATIO:
        result["warning"] = (f"liczba rekordów spadła z {before} do {after}; poprzedni wynik w {prev} "
                             "(sprawdź, czy źródło nie zmieniło formatu)")
    return result


def _is_xlsx(content: bytes) -> bool:
    return content[:4] == b"PK\x03\x04"


# --- Interreg ------------------------------------------------------------------
def refresh_interreg(args, prev_state: dict) -> dict:
    raw = Path(args.raw_dir) / "interreg"
    out = Path(args.out_dir) / "interreg.jsonl"
    store = interreg.RawStore(raw)
    file_meta = store.load("file") or {}
    local_ok = bool(file_meta) and sha256_file(Path(file_meta.get("path", ""))) == file_meta.get("sha256")
    result: dict = {}

    if args.offline:
        if not local_ok:
            raise FileNotFoundError(f"brak poprawnego zapisanego pliku w {raw}")
        result["download"] = "offline"
    else:
        page = fetch(interreg.LIST_URL)
        file_url = interreg.find_xlsx_link(page.text)
        if not file_url:
            raise interreg.FormatChanged(f"na stronie {interreg.LIST_URL} nie ma linku do pliku .xlsx")
        result["file_url"] = file_url
        same_file = local_ok and file_meta.get("url") == file_url
        if same_file and not args.force:
            log(f"interreg: plik {file_url.rsplit('/', 1)[-1]} już pobrany (SHA-256 zgodne), pomijam pobieranie")
            result["download"] = "skipped_already_have"
        elif args.dry_run:
            log(f"interreg: [dry-run] pobrałbym {file_url}")
            return {**result, "download": "would_download"}
        else:
            if not local_ok and file_meta:
                log("interreg: zapisany plik uszkodzony albo brak go na dysku, pobieram ponownie")
            log(f"interreg: pobieram {file_url}")
            resp = fetch_bytes(file_url)
            if not _is_xlsx(resp.content):
                raise interreg.FormatChanged(f"{file_url} nie jest plikiem XLSX ({len(resp.content)} B); "
                                             "zostawiam poprzedni plik")
            new_sha = hashlib.sha256(resp.content).hexdigest()
            if new_sha == file_meta.get("sha256") and local_ok:
                log("interreg: treść pliku taka sama jak zapisana (inna nazwa/URL)")
            store.save_page(page)
            store.save_file(resp)
            result["download"] = "downloaded"
        file_meta = store.load("file") or {}

    input_sha = file_meta.get("sha256")
    result["input_sha256"] = input_sha
    unchanged = (input_sha == prev_state.get("input_sha256") and out.exists()
                 and sha256_file(out) == prev_state.get("output_sha256"))
    if unchanged and not args.force:
        log("interreg: dane wejściowe bez zmian, wynik aktualny, pomijam przebudowę")
        return {**result, "rebuild": "skipped_unchanged", "records": count_lines(out),
                "output_sha256": prev_state.get("output_sha256")}
    if args.dry_run:
        log("interreg: [dry-run] przebudowałbym wynik")
        return {**result, "rebuild": "would_rebuild"}
    argv = ["--offline", "--raw-dir", str(raw), "--out", str(out), "--csv", str(out.with_suffix(".csv"))]
    return {**result, "rebuild": "rebuilt", **rebuild(out, lambda: interreg.main(argv))}


# --- NCBR ----------------------------------------------------------------------
def _age_hours(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600


def _cached_detail_count(raw: Path) -> int:
    d = raw / "detail"
    return sum(1 for _ in d.glob("*.html")) if d.exists() else 0


def refresh_ncbr(args, prev_state: dict) -> dict:
    raw = Path(args.raw_dir) / "ncbr"
    out = Path(args.out_dir) / "ncbr.jsonl"
    store = ncbr.RawStore(raw)
    cached = store.get("list")
    result: dict = {"detail_pages_cached_before": _cached_detail_count(raw)}

    if args.offline:
        if not cached:
            raise FileNotFoundError(f"brak zapisanej strony listy w {raw}")
        result["list"] = "offline"
    else:
        age = _age_hours(cached[1].get("fetched_at")) if cached else None
        if cached and age is not None and age < args.max_age and not args.force:
            log(f"ncbr: lista pobrana {age:.1f} h temu (< {args.max_age} h), nie pobieram ponownie")
            result["list"] = "skipped_fresh"
        elif args.dry_run:
            log("ncbr: [dry-run] pobrałbym stronę listy i nowe strony szczegółów")
            return {**result, "list": "would_download"}
        else:
            log(f"ncbr: pobieram stronę listy {ncbr.LIST_URL}")
            resp = fetch(ncbr.LIST_URL)
            if not ncbr.parse_list(resp.text):
                raise RuntimeError("nowa strona listy NCBR nie zawiera żadnych kart; zostawiam poprzednią")
            store.put("list", resp)
            result["list"] = "downloaded"
        cached = store.get("list")

    list_sha = cached[1].get("sha256") if cached else None
    result["input_sha256"] = list_sha
    unchanged = (list_sha == prev_state.get("input_sha256") and out.exists()
                 and sha256_file(out) == prev_state.get("output_sha256"))
    if unchanged and not args.force:
        log("ncbr: lista bez zmian, wynik aktualny, pomijam przebudowę")
        return {**result, "rebuild": "skipped_unchanged", "records": count_lines(out),
                "output_sha256": prev_state.get("output_sha256")}
    if args.dry_run:
        log("ncbr: [dry-run] przebudowałbym wynik (pobierając brakujące strony szczegółów)")
        return {**result, "rebuild": "would_rebuild"}

    # list page is already saved above, so the connector reads it from disk; detail pages
    # already on disk are reused and only new cards are fetched (or none with --offline)
    argv = ["--raw-dir", str(raw), "--out", str(out), "--csv", str(out.with_suffix(".csv")),
            "--delay", str(args.delay)]
    if args.offline:
        argv.append("--offline")
    if args.force:
        # refetch detail pages too, but keep the list we have just downloaded
        argv.append("--refresh")
    res = {**result, "rebuild": "rebuilt", **rebuild(out, lambda: ncbr.main(argv))}
    res["detail_pages_new"] = _cached_detail_count(raw) - result["detail_pages_cached_before"]
    return res


SOURCES = {"interreg": refresh_interreg, "ncbr": refresh_ncbr}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", nargs="+", choices=list(SOURCES), default=list(SOURCES),
                    help="które źródła odświeżyć (domyślnie wszystkie)")
    ap.add_argument("--raw-dir", default=str(DATA / "raw"))
    ap.add_argument("--out-dir", default=str(DATA / "normalized"))
    ap.add_argument("--max-age", type=float, default=24.0,
                    help="NCBR: po ilu godzinach pobrać stronę listy ponownie (domyślnie 24)")
    ap.add_argument("--delay", type=float, default=1.0, help="NCBR: sekundy między zapytaniami")
    ap.add_argument("--force", action="store_true", help="pobierz i przebuduj wszystko, ignorując cache")
    ap.add_argument("--offline", action="store_true", help="bez sieci, tylko z zapisanych plików")
    ap.add_argument("--dry-run", action="store_true", help="pokaż, co by zrobiono, nic nie zapisuj")
    args = ap.parse_args(argv)
    if args.offline and args.force:
        ap.error("--offline i --force wzajemnie się wykluczają")

    with Lock(LOCK_FILE):
        state = read_json(STATE_FILE)
        sources_state = state.setdefault("sources", {})
        history = state.setdefault("history", [])
        failed, warned = [], []
        for name in args.sources:
            started = time.monotonic()
            log(f"=== {name} ===")
            prev = sources_state.get(name, {})
            try:
                res = SOURCES[name](args, prev)
                res["ok"] = True
            except (FetchError, OSError, RuntimeError, interreg.FormatChanged) as e:
                log(f"{name}: BŁĄD: {e}")
                res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
                failed.append(name)
            res["seconds"] = round(time.monotonic() - started, 1)
            res["at"] = now_iso()
            if res.get("warning"):
                log(f"{name}: UWAGA: {res['warning']}")
                warned.append(name)
            summary = {k: res.get(k) for k in ("download", "list", "rebuild", "records", "detail_pages_new") if res.get(k) is not None}
            log(f"{name}: {'OK' if res['ok'] else 'BŁĄD'} {summary} w {res['seconds']} s")
            if args.dry_run:
                continue
            if res["ok"]:
                sources_state[name] = {**prev, **res, "last_success": res["at"]}
            else:
                sources_state[name] = {**prev, "last_error": res["error"], "last_error_at": res["at"]}
            history.append({"source": name, **{k: res.get(k) for k in
                            ("at", "ok", "download", "list", "rebuild", "records", "error", "warning", "seconds")
                            if res.get(k) is not None}})
        if not args.dry_run:
            state["history"] = history[-HISTORY_LIMIT:]
            state["last_run"] = now_iso()
            write_json_atomic(STATE_FILE, state)

    if failed:
        log(f"nie udało się: {', '.join(failed)}")
    return 1 if failed or warned else 0


if __name__ == "__main__":
    sys.exit(main())
