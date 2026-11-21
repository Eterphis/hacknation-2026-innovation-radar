"""Odświeżenie danych ze wszystkich źródeł z rejestru (REGISTRY): Interreg, NCBR, crawler stron
(config/sites.json) i konektory API, które są w repozytorium.

    python -X utf8 -m radar.refresh                       # wszystkie źródła, tylko to, co się zmieniło
    python -X utf8 -m radar.refresh --due-only            # tylko źródła, którym minął termin (scheduler)
    python -X utf8 -m radar.refresh --list                # rejestr źródeł i terminy
    python -X utf8 -m radar.refresh --category nauka      # źródła i witryny jednej kategorii
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
- po przebudowie rekordy trafiają do bazy `data/radar.db` (`radar.store`): nowe, zmienione,
  usunięte ze źródła; każde uruchomienie zapisuje się w tabeli `refresh_runs`;
- błąd jednego źródła nie zatrzymuje drugiego.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import os
import shutil
import socket
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import store
from .http import FetchError, fetch, fetch_bytes
from .sources import interreg, ncbr

DATA = Path("data")
STATE_FILE = DATA / "refresh_state.json"  # legacy, read once for migration
LOCK_FILE = DATA / ".refresh.lock"
LOCK_STALE_SECONDS = 6 * 3600
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
                # a PID is only meaningful on the host (or container) that wrote it
                other_host = info.get("host") not in (None, socket.gethostname())
                if age < LOCK_STALE_SECONDS and (other_host or _pid_alive(int(info.get("pid", 0)))):
                    raise SystemExit(f"odświeżanie już trwa (pid {info.get('pid')} na {info.get('host')}, od {info.get('started')}); "
                                     f"jeśli to nieprawda, usuń {self.path}")
                log(f"przejmuję porzuconą blokadę {self.path}")
                self.path.unlink(missing_ok=True)
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"pid": os.getpid(), "host": socket.gethostname(), "started": now_iso()}, fh)
            self.held = True
            return self
        raise SystemExit(f"nie udało się założyć blokady {self.path}")

    def __exit__(self, *exc) -> None:
        if not self.held:
            return
        info = read_json(self.path)
        # release only our own lock: another process may have taken over a stale one meanwhile
        if info.get("pid") == os.getpid() and info.get("host") == socket.gethostname():
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


# --- web crawler -----------------------------------------------------------------
def refresh_web(args, prev_state: dict, conn: sqlite3.Connection | None = None) -> dict:
    """Sites from config/sites.json whose interval has passed; the crawler writes to the database itself."""
    from .crawl.crawler import crawl_due, totals
    from .crawl.sites import load_sites

    sites = load_sites(args.sites_config)
    if args.category:
        sites = [s for s in sites if s.category in args.category]
    if not sites:
        log("web: brak włączonych witryn w konfiguracji")
        return {"download": "no_sites", "rebuild": "skipped_unchanged", "records": 0}
    if args.offline:
        return {"download": "offline", "rebuild": "skipped_unchanged", "records": 0}
    if args.dry_run:
        log(f"web: [dry-run] przeszedłbym witryny: {', '.join(s.id for s in sites)}")
        return {"download": "would_crawl", "rebuild": "would_rebuild"}
    results = crawl_due(conn, sites, raw_root=Path(args.raw_dir) / "web", force=args.force)
    t = totals(results)
    for r in results:
        log(f"web/{r['site']}: {r['status']} pobrane {r['fetched']}, nowe {r['added']}, zmienione {r['changed']}, "
            f"304 {r['not_modified']}, pominięte {r['skipped']}" + (f" ({r['error']})" if r["error"] else ""))
    res = {"download": "crawled", "rebuild": "rebuilt" if results else "skipped_unchanged",
           "records": conn.execute("SELECT COUNT(*) FROM records WHERE source LIKE 'web\\_%' ESCAPE '\\' "
                                   "AND removed_at IS NULL").fetchone()[0],
           "added": t["added"], "changed": t["changed"], "removed": t["removed"],
           "sites": [{k: r[k] for k in ("site", "status", "error", "fetched", "added", "changed", "not_modified")}
                     for r in results]}
    if t["blocked_sites"]:
        res["warning"] = f"witryny zablokowane (nie obchodzimy): {', '.join(t['blocked_sites'])}"
    if results and len(t["failed_sites"]) == len(results):
        raise RuntimeError(f"wszystkie witryny zakończone błędem: {', '.join(t['failed_sites'])}")
    return res


# --- generic adapter for connectors with main(argv) -------------------------------
def connector_step(name: str, module: str, extra: tuple[str, ...] = (), incremental: bool = False,
                   manual_import: bool = False):
    """Run `module.main(--raw-dir --out --csv [--offline])` and keep the previous output (rebuild()).

    incremental: the connector harvests a time window, so a smaller output than last time is normal.
    manual_import: the input is a file a person drops in data/import/; none there yet is not an error."""
    def run(args, prev_state: dict) -> dict:
        mod = importlib.import_module(module)
        raw = Path(args.raw_dir) / name
        out = Path(args.out_dir) / f"{name}.jsonl"
        if args.dry_run:
            log(f"{name}: [dry-run] uruchomiłbym {module}")
            return {"rebuild": "would_rebuild"}
        argv = ["--raw-dir", str(raw), "--out", str(out), "--csv", str(out.with_suffix(".csv")), *extra]
        if args.offline:
            argv.append("--offline")
        try:
            res = {"download": "offline" if args.offline else "connector", "rebuild": "rebuilt",
                   **rebuild(out, lambda: mod.main(argv))}
        except FileNotFoundError as e:
            if not manual_import:
                raise
            log(f"{name}: brak pliku do importu, pomijam ({e})")
            return {"download": "no_import_files", "rebuild": "skipped_unchanged", "records": count_lines(out)}
        res["input_sha256"] = res.get("output_sha256")
        if incremental:
            res.pop("warning", None)
        return res
    return run


@dataclass(frozen=True)
class Source:
    id: str                      # name used on the command line and in refresh_runs
    source_id: str | None        # `source` of the records; None = every source found in the output
    category: str                # nauka | projekty | biznes | administracja | mixed
    kind: str                    # api | web | import
    interval_hours: float        # --due-only: run again after this many hours
    run: Callable
    writes_db: bool = False      # True: the step writes to the database itself (crawler)
    incremental: bool = False    # harvests a time window: records missing from it are NOT removed

    @property
    def output(self) -> str:
        return f"{self.id}.jsonl"


# Sources from the brief. Connectors that are not in this checkout yet are skipped (see available()).
REGISTRY: list[Source] = [
    Source("interreg", "interreg_pl", "projekty", "api", 24, refresh_interreg),
    Source("ncbr", "ncbr_sukcesy", "projekty", "api", 24, refresh_ncbr),
    Source("web", None, "mixed", "web", 1, refresh_web, writes_db=True),  # per-site schedule in crawl_due
]
PLANNED: list[tuple[str, str, str, str, float, tuple[str, ...], bool]] = [
    # (id, module, category, kind, interval_hours, extra argv, incremental); source ids come from the records
    # windowed harvests overlap the interval so nothing falls between two runs
    ("bibliotekanauki", "radar.sources.bibliotekanauki", "nauka", "api", 168, ("--days", "10"), True),
    ("openalex", "radar.sources.openalex", "nauka", "api", 168, ("--days", "30"), True),
    ("radon", "radar.sources.radon", "projekty", "api", 168, (), False),
    ("epo", "radar.sources.epo", "nauka", "api", 168, (), False),
    ("cordis", "radar.sources.cordis", "projekty", "api", 168, (), False),
    ("fe_projects", "radar.sources.fe_projects", "projekty", "api", 168, (), False),
    ("uprp_import", "radar.sources.uprp_import", "nauka", "import", 24, (), False),
]
for _id, _module, _cat, _kind, _hours, _extra, _incr in PLANNED:
    if importlib.util.find_spec(_module) is not None:
        REGISTRY.append(Source(_id, None, _cat, _kind, _hours,
                               connector_step(_id, _module, _extra, _incr, manual_import=_kind == "import"),
                               incremental=_incr))
SOURCES = {s.id: s for s in REGISTRY}
FAILED_RETRY_HOURS = 6


def previous_state(conn, name: str) -> dict:
    """Last good run from the database; falls back to the old refresh_state.json once."""
    prev = store.last_successful_run(conn, name)
    if not prev:
        prev = (read_json(STATE_FILE).get("sources") or {}).get(name, {})
    return prev


def is_due(conn, src: Source) -> tuple[bool, str]:
    """Due when never run, when the interval passed since the last run, or a failed run is older than 6 h."""
    row = conn.execute("SELECT at, ok FROM refresh_runs WHERE source=? ORDER BY at DESC, id DESC LIMIT 1", (src.id,)).fetchone()
    if row is None:
        return True, "nigdy nie uruchamiane"
    age = _age_hours(row["at"])
    if age is None:
        return True, "nieczytelna data ostatniego przebiegu"
    limit = src.interval_hours if row["ok"] else min(src.interval_hours, FAILED_RETRY_HOURS)
    if age >= limit:
        return True, f"ostatnio {age:.1f} h temu (termin co {limit:g} h)"
    return False, f"ostatnio {age:.1f} h temu, następny za {limit - age:.1f} h"


def backfill_categories(conn) -> int:
    """Records loaded before categories existed (database v1) get their source's category."""
    n = 0
    with conn:
        for s in REGISTRY:
            if s.source_id and s.category != "mixed":
                n += conn.execute("UPDATE records SET category=? WHERE source=? AND category IS NULL",
                                  (s.category, s.source_id)).rowcount
    return n


def load_into_db(conn, src: Source, out: Path, res: dict, force_removal: bool = False) -> None:
    """Upsert the source's JSONL after a rebuild, or when the database has none of it yet."""
    if not out.exists():
        return
    recs = store.read_jsonl(out)
    sids = [src.source_id] if src.source_id else sorted({r.get("source") for r in recs if r.get("source")})
    in_db = all(conn.execute("SELECT 1 FROM records WHERE source=? LIMIT 1", (sid,)).fetchone() for sid in sids)
    if res.get("rebuild") != "rebuilt" and in_db and sids:
        res.update(added=0, changed=0, removed=0)
        return
    total = {"added": 0, "changed": 0, "removed": 0, "restored": 0, "removal_skipped": 0}
    category = None if src.category == "mixed" else src.category
    for sid in sids:
        counts = store.upsert_source(conn, sid, [r for r in recs if r.get("source") == sid],
                                     mark_removed=not src.incremental, category=category, force_removal=force_removal)
        for k in total:
            total[k] += counts[k]
    res.update({k: total[k] for k in ("added", "changed", "removed", "restored")})
    if total["removal_skipped"]:
        res["warning"] = (f"{total['removal_skipped']} rekordów zniknęło ze źródła naraz (ponad połowa); nie oznaczam ich "
                          "jako usuniętych. Sprawdź źródło i uruchom z --force, jeśli to prawda.")
    log(f"{src.id}: baza: nowe {total['added']}, zmienione {total['changed']}, "
        f"usunięte ze źródła {total['removed']}, przywrócone {total['restored']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", nargs="+", choices=list(SOURCES), default=list(SOURCES),
                    help="które źródła odświeżyć (domyślnie wszystkie)")
    ap.add_argument("--due-only", action="store_true",
                    help="tylko źródła, którym minął termin (według ostatniego wpisu w refresh_runs)")
    ap.add_argument("--category", nargs="+", choices=("nauka", "projekty", "biznes", "administracja"),
                    help="tylko źródła i witryny z tych kategorii")
    ap.add_argument("--sites-config", default=None, help="plik witryn crawlera (domyślnie config/sites.json)")
    ap.add_argument("--list", action="store_true", help="wypisz rejestr źródeł z terminami i zakończ")
    ap.add_argument("--raw-dir", default=str(DATA / "raw"))
    ap.add_argument("--out-dir", default=str(DATA / "normalized"))
    ap.add_argument("--db", default=None, help=f"baza SQLite (domyślnie $RADAR_DB albo {store.DEFAULT_DB})")
    ap.add_argument("--max-age", type=float, default=24.0,
                    help="NCBR: po ilu godzinach pobrać stronę listy ponownie (domyślnie 24)")
    ap.add_argument("--delay", type=float, default=1.0, help="NCBR: sekundy między zapytaniami")
    ap.add_argument("--force", action="store_true", help="pobierz i przebuduj wszystko, ignorując cache")
    ap.add_argument("--offline", action="store_true", help="bez sieci, tylko z zapisanych plików")
    ap.add_argument("--dry-run", action="store_true", help="pokaż, co by zrobiono, nic nie zapisuj")
    args = ap.parse_args(argv)
    if args.offline and args.force:
        ap.error("--offline i --force wzajemnie się wykluczają")

    db_path = args.db or store.default_db()
    selected = [SOURCES[n] for n in args.sources]
    if args.category:
        selected = [s for s in selected if s.category in args.category or s.category == "mixed"]

    if args.list:
        conn = store.connect(db_path)
        for s in REGISTRY:
            due, why = is_due(conn, s)
            print(f"{s.id:<16} {s.kind:<7} {s.category:<14} co {s.interval_hours:g} h  "
                  f"{'DO URUCHOMIENIA' if due else 'czeka'}: {why}")
        conn.close()
        return 0

    with Lock(LOCK_FILE):
        conn = store.connect(db_path)
        if not args.dry_run:
            backfill_categories(conn)
        failed, warned = [], []
        for src in selected:
            name = src.id
            if args.due_only and not args.force:
                due, why = is_due(conn, src)
                if not due:
                    log(f"{name}: pomijam, {why}")
                    continue
                log(f"{name}: {why}")
            started = time.monotonic()
            log(f"=== {name} ===")
            prev = previous_state(conn, name)
            try:
                res = src.run(args, prev, conn) if src.writes_db else src.run(args, prev)
                if not args.dry_run and not src.writes_db:
                    load_into_db(conn, src, Path(args.out_dir) / src.output, res, force_removal=args.force)
                res["ok"] = True
            except (FetchError, OSError, RuntimeError, ValueError, sqlite3.Error, interreg.FormatChanged) as e:
                log(f"{name}: BŁĄD: {e}")
                res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
                failed.append(name)
            res["seconds"] = round(time.monotonic() - started, 1)
            res["at"] = now_iso()
            res.setdefault("download", res.get("list"))
            if res.get("warning"):
                log(f"{name}: UWAGA: {res['warning']}")
                warned.append(name)
            summary = {k: res.get(k) for k in ("download", "rebuild", "records", "added", "changed", "removed",
                                               "detail_pages_new") if res.get(k) is not None}
            log(f"{name}: {'OK' if res['ok'] else 'BŁĄD'} {summary} w {res['seconds']} s")
            if not args.dry_run:
                store.add_refresh_run(conn, name, res)
        conn.close()

    if failed:
        log(f"nie udało się: {', '.join(failed)}")
    return 1 if failed or warned else 0


if __name__ == "__main__":
    sys.exit(main())
