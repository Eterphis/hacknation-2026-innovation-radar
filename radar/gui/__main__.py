"""Radar innowacji – local viewer of harvested data (standard library only).

Shows exactly what the connectors wrote to the normalized JSONL files, record by record, together
with where each record was loaded from (source URL or file, fetch times, connector, cached raw files).

Run:  python -X utf8 -m radar.gui                     -> database data/radar.db, http://127.0.0.1:8765
      python -X utf8 -m radar.gui --host 0.0.0.0        -> reachable from other machines / Docker
      python -X utf8 -m radar.gui --data                -> no database: every data/normalized/*.jsonl
      python -X utf8 -m radar.gui --data data/normalized/interreg.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote

from .. import store as db
from ..sources.ncbr import _file_key, _slug

STATIC = Path(__file__).parent / "static"
KEY_RE = r"([a-z0-9_]{1,40})/([a-z0-9][a-z0-9-]{0,400})"
LEADING_ROLES = ("beneficiary", "lead_partner")


def raw_files(rec: dict, ncbr_raw_dir: Path | None) -> dict:
    """Where the raw input behind a record sits on disk (the connector's cache)."""
    found = dict((rec.get("provenance") or {}).get("raw_files") or {})
    if not found and rec.get("source") == "ncbr_sukcesy" and ncbr_raw_dir:
        found = {"list_page": str(ncbr_raw_dir / "list.html")}
        slug = _slug(rec.get("url"))
        if slug:
            found["detail_page"] = str(ncbr_raw_dir / "detail" / f"{_file_key(slug)}.html")
    return {k: {"path": v, "exists": Path(v).exists()} for k, v in found.items() if v}


class DbRecordStore:
    """Records from the SQLite database (radar.store); queried on every request, so a refresh
    running next to the viewer shows up without a restart."""

    def __init__(self, db_path: Path, ncbr_raw_dir: Path | None = None) -> None:
        self.db_path = Path(db_path)
        self.ncbr_raw_dir = ncbr_raw_dir
        db.connect(self.db_path).close()  # create / migrate once; afterwards the viewer only reads

    def _conn(self):
        # read-only: never waits for the write lock of a harvest running next to the viewer
        return db.connect_readonly(self.db_path)

    def meta(self, light: bool = False) -> dict:
        conn = self._conn()
        try:
            if light:  # polled every few seconds by the viewer: two cheap queries
                n = conn.execute("SELECT COUNT(*) FROM records WHERE removed_at IS NULL").fetchone()[0]
                return {"db": str(self.db_path), "records": n, "refresh_runs": db.refresh_runs(conn, 1)}
            st = db.stats(conn)
            return {"db": str(self.db_path), "files": [{"path": str(self.db_path), "records": st["records"]}],
                    "loaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "records": st["records"], "removed": st["removed"], "sources": st["sources"],
                    "source_ids": st["source_ids"], "quality": st["quality"], "categories": st["categories"],
                    "voivodeships": db.voivodeships(conn), "first_seen_min": st["first_seen_min"],
                    "search": "fts" if st["fts"] else "like",
                    "refresh_runs": db.refresh_runs(conn, 10)}
        finally:
            conn.close()

    def summary(self, query: dict | None = None) -> list[dict] | dict:
        """Without `limit`: every matching row (list). With `limit`/`offset`: one page as
        {"total", "offset", "limit", "rows"}, so the browser never has to hold the whole database."""
        query = query or {}
        filters = dict(q=query.get("q"), source=query.get("source"), quality=query.get("quality"),
                       category=query.get("category"), voivodeship=query.get("voivodeship"),
                       include_removed=query.get("removed") == "1")
        page = _page(query)
        conn = self._conn()
        try:
            if page is None:
                return [db.summary_row(r) for r in db.list_records(conn, **filters)]
            limit, offset = page
            rows = [db.summary_row(r) for r in db.list_records(conn, **filters, limit=limit, offset=offset)]
            return {"total": db.count_records(conn, **filters), "offset": offset, "limit": limit, "rows": rows}
        finally:
            conn.close()

    def record(self, key: str) -> dict | None:
        source, _, record_id = key.partition("/")
        conn = self._conn()
        try:
            got = db.get_record(conn, source, record_id)
        finally:
            conn.close()
        if got is None:
            return None
        return {**got, "raw_files": raw_files(got["record"], self.ncbr_raw_dir), "data_file": str(self.db_path)}


class RecordStore:
    """Normalized records from one or more JSONL files, read once at start-up (read-only)."""

    def __init__(self, data_paths: list[Path] | Path, ncbr_raw_dir: Path | None = None) -> None:
        self.data_paths = [data_paths] if isinstance(data_paths, Path) else list(data_paths)
        self.ncbr_raw_dir = ncbr_raw_dir
        self.records: list[dict] = []
        self.file_of: dict[str, Path] = {}
        self.files: list[dict] = []
        for path in self.data_paths:
            recs = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]
            self.files.append({"path": str(path), "records": len(recs),
                               "modified": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")})
            for r in recs:
                self.records.append(r)
                self.file_of[self.key(r)] = path
        self.by_key = {self.key(r): r for r in self.records}
        self.loaded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def key(rec: dict) -> str:
        return f"{rec.get('source')}/{rec['record_id']}"

    def raw_files(self, rec: dict) -> dict:
        return raw_files(rec, self.ncbr_raw_dir)

    def meta(self, light: bool = False) -> dict:
        return {
            "files": self.files,
            "loaded_at": self.loaded_at,
            "records": len(self.records),
            "sources": _count(r.get("source_name") for r in self.records),
            "source_ids": {r.get("source"): r.get("source_name") for r in self.records},
            "quality": _count((r.get("quality") or {}).get("status") for r in self.records),
            "categories": _count((r.get("extra") or {}).get("category") or "(brak)" for r in self.records),
            "voivodeships": sorted({v for r in self.records for v in (r.get("region") or {}).get("voivodeships") or []}),
            "first_seen_min": None,
        }

    def summary(self, query: dict | None = None) -> list[dict] | dict:
        query = query or {}
        rows = [r for r in self._rows() if _matches(r, query)]
        page = _page(query)
        if page is None:
            return rows
        limit, offset = page
        return {"total": len(rows), "offset": offset, "limit": limit, "rows": rows[offset:offset + limit]}

    def _rows(self) -> list[dict]:
        rows = []
        for r in self.records:
            leads = [o["name"] for o in r.get("organizations") or [] if o.get("role") in LEADING_ROLES]
            people = [p["source_text"] for p in r.get("people") or [] if p.get("role") == "beneficiary"]
            q = r.get("quality") or {}
            region = r.get("region") or {}
            rows.append({
                "key": self.key(r),
                "source": r.get("source"),
                "title": r.get("title"),
                "beneficiary": "; ".join(leads or people),
                "voivodeships": region.get("voivodeships") or [],
                "country": region.get("country"),
                "programme": (r.get("funding") or {}).get("programme"),
                "contest": (r.get("funding") or {}).get("contest"),
                "quality": q.get("status"),
                "category": (r.get("extra") or {}).get("category"),
            })
        return rows

    def record(self, key: str) -> dict | None:
        rec = self.by_key.get(key)
        if rec is None:
            return None
        return {"record": rec, "raw_files": self.raw_files(rec), "data_file": str(self.file_of[key])}


MAX_PAGE = 1000


def _page(query: dict) -> tuple[int, int] | None:
    if "limit" not in query:
        return None
    try:
        limit = max(1, min(MAX_PAGE, int(query.get("limit") or 200)))
        offset = max(0, int(query.get("offset") or 0))
    except ValueError:
        limit, offset = 200, 0
    return limit, offset


def _matches(row: dict, query: dict) -> bool:
    """Filters of /api/records for the file mode (the database mode filters in SQL)."""
    q = (query.get("q") or "").strip().lower()
    cat = query.get("category")
    if q and q not in " ".join(str(row.get(k) or "") for k in ("title", "beneficiary", "programme", "contest")).lower():
        return False
    if cat and (row.get("category") is not None if cat == db.NO_CATEGORY else row.get("category") != cat):
        return False
    for key in ("source", "quality"):
        if query.get(key) and row.get(key) != query[key]:
            return False
    return not query.get("voivodeship") or query["voivodeship"] in row.get("voivodeships", [])


def _count(values) -> dict:
    out: dict = {}
    for v in values:
        key = v if v is not None else "(brak)"
        out[key] = out.get(key, 0) + 1
    return out


def make_handler(store: "RecordStore | DbRecordStore"):
    class Handler(BaseHTTPRequestHandler):
        server_version = "RadarViewer/0.3"

        def log_message(self, fmt, *args):
            if not self.path.startswith("/api/records/"):
                sys.stderr.write("%s %s\n" % (self.command, self.path))

        def _send(self, status: int, body: bytes, ctype: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, status: int = 200) -> None:
            self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            if path == "/api/meta":
                light = "light=1" in self.path.partition("?")[2].split("&")
                return self._json(store.meta(light=light))
            if path == "/api/records":
                qs = parse_qs(self.path.partition("?")[2])
                return self._json(store.summary({k: v[0] for k, v in qs.items()}))
            m = re.fullmatch(rf"/api/records/{KEY_RE}", unquote(path))
            if m:
                data = store.record(f"{m.group(1)}/{m.group(2)}")
                return self._json(data) if data else self._json({"error": "not found"}, 404)
            self._json({"error": "not found"}, 404)

    return Handler


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=None, help=f"baza SQLite (domyślnie $RADAR_DB albo {db.DEFAULT_DB})")
    ap.add_argument("--data", nargs="*", default=None,
                    help="tryb bez bazy: pliki JSONL (bez nazw: każdy data/normalized/*.jsonl)")
    ap.add_argument("--ncbr-raw-dir", default="data/raw/ncbr", help="NCBR raw page cache (shown as provenance)")
    ap.add_argument("--host", default="127.0.0.1", help="adres nasłuchu (w Dockerze 0.0.0.0)")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args(argv)

    if args.data is not None:
        paths = [Path(p) for p in args.data] or sorted(Path("data/normalized").glob("*.jsonl"))
        missing = [p for p in paths if not p.exists()]
        if not paths or missing:
            print("brak danych: najpierw uruchom `python -X utf8 -m radar.refresh`"
                  + (f" (nie ma: {', '.join(map(str, missing))})" if missing else ""), file=sys.stderr)
            return 2
        store = RecordStore(paths, Path(args.ncbr_raw_dir))
        what = f"{len(store.records)} rekordów z {len(paths)} plików"
    else:
        db_path = Path(args.db or db.default_db())
        store = DbRecordStore(db_path, Path(args.ncbr_raw_dir))
        n = store.meta()["records"]
        what = f"baza {db_path}, {n} rekordów" + ("" if n else " (pusta: uruchom `python -X utf8 -m radar.refresh`)")
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(store))
    print(f"Radar innowacji: {what}, http://{args.host}:{args.port}", file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
