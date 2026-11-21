"""Radar innowacji – local viewer of harvested data (standard library only).

Shows exactly what the connectors wrote to the normalized JSONL files, record by record, together
with where each record was loaded from (source URL or file, fetch times, connector, cached raw files).

Run:  python -X utf8 -m radar.gui                     -> all data/normalized/*.jsonl, http://127.0.0.1:8765
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
from urllib.parse import unquote

from ..sources.ncbr import _file_key, _slug

STATIC = Path(__file__).parent / "static"
KEY_RE = r"([a-z0-9_]{1,40})/([a-z0-9][a-z0-9-]{0,400})"
LEADING_ROLES = ("beneficiary", "lead_partner", "applicant")


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
        """Where the raw input behind a record sits on disk (the connector's cache)."""
        found = dict((rec.get("provenance") or {}).get("raw_files") or {})
        if not found and rec.get("source") == "ncbr_sukcesy" and self.ncbr_raw_dir:
            found = {"list_page": str(self.ncbr_raw_dir / "list.html")}
            slug = _slug(rec.get("url"))
            if slug:
                found["detail_page"] = str(self.ncbr_raw_dir / "detail" / f"{_file_key(slug)}.html")
        return {k: {"path": v, "exists": Path(v).exists()} for k, v in found.items() if v}

    def meta(self) -> dict:
        return {
            "files": self.files,
            "loaded_at": self.loaded_at,
            "records": len(self.records),
            "sources": _count(r.get("source_name") for r in self.records),
            "source_ids": {r.get("source"): r.get("source_name") for r in self.records},
            "quality": _count((r.get("quality") or {}).get("status") for r in self.records),
        }

    def summary(self) -> list[dict]:
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
            })
        return rows

    def record(self, key: str) -> dict | None:
        rec = self.by_key.get(key)
        if rec is None:
            return None
        return {"record": rec, "raw_files": self.raw_files(rec), "data_file": str(self.file_of[key])}


def _count(values) -> dict:
    out: dict = {}
    for v in values:
        key = v if v is not None else "(brak)"
        out[key] = out.get(key, 0) + 1
    return out


def make_handler(store: RecordStore):
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
                return self._json(store.meta())
            if path == "/api/records":
                return self._json(store.summary())
            m = re.fullmatch(rf"/api/records/{KEY_RE}", unquote(path))
            if m:
                data = store.record(f"{m.group(1)}/{m.group(2)}")
                return self._json(data) if data else self._json({"error": "not found"}, 404)
            self._json({"error": "not found"}, 404)

    return Handler


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", nargs="*", default=None,
                    help="normalized JSONL files (default: every data/normalized/*.jsonl)")
    ap.add_argument("--ncbr-raw-dir", default="data/raw/ncbr", help="NCBR raw page cache (shown as provenance)")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args(argv)

    paths = [Path(p) for p in args.data] if args.data else sorted(Path("data/normalized").glob("*.jsonl"))
    missing = [p for p in paths if not p.exists()]
    if not paths or missing:
        print("brak danych: najpierw uruchom `python -X utf8 -m radar.sources.ncbr` lub `... radar.sources.interreg`"
              + (f" (nie ma: {', '.join(map(str, missing))})" if missing else ""), file=sys.stderr)
        return 2
    store = RecordStore(paths, Path(args.ncbr_raw_dir))
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(store))
    print(f"Radar innowacji: {len(store.records)} rekordów z {len(paths)} plików, http://127.0.0.1:{args.port}", file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
