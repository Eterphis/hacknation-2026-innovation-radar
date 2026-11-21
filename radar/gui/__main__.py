"""Radar innowacji – local viewer of harvested data (standard library only).

Shows exactly what the connector wrote to the normalized JSONL, record by record, together with
where each record was loaded from (source URL, fetch times, connector version, cached raw page).

Run:  python -X utf8 -m radar.gui                                   -> http://127.0.0.1:8765
      python -X utf8 -m radar.gui --data data/normalized/ncbr.jsonl --raw-dir data/raw/ncbr
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
RECORD_ID_RE = r"[a-z0-9][a-z0-9-]{0,400}"


class RecordStore:
    """Normalized records from one JSONL file, read once at start-up (read-only)."""

    def __init__(self, data_path: Path, raw_dir: Path | None = None) -> None:
        self.data_path = data_path
        self.raw_dir = raw_dir
        lines = [line for line in data_path.read_text("utf-8").splitlines() if line.strip()]
        self.records = [json.loads(line) for line in lines]
        self.by_id = {r["record_id"]: r for r in self.records}
        self.loaded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def raw_files(self, rec: dict) -> dict:
        """Where the raw pages behind a record sit on disk (the connector's cache)."""
        if not self.raw_dir:
            return {}
        out = {"list_page": str(self.raw_dir / "list.html")}
        slug = _slug(rec.get("url"))
        if slug:
            out["detail_page"] = str(self.raw_dir / "detail" / f"{_file_key(slug)}.html")
        return {k: {"path": v, "exists": Path(v).exists()} for k, v in out.items()}

    def meta(self) -> dict:
        prov = [r.get("provenance") or {} for r in self.records]
        fetched = sorted(p.get("detail_fetched_at") for p in prov if p.get("detail_fetched_at"))
        count = lambda key: _count(r.get(key) for r in self.records)  # noqa: E731
        return {
            "file": str(self.data_path),
            "file_modified": datetime.fromtimestamp(self.data_path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds"),
            "loaded_at": self.loaded_at,
            "records": len(self.records),
            "sources": count("source_name"),
            "schemas": count("schema"),
            "connectors": _count(p.get("connector") for p in prov),
            "list_urls": count("list_url"),
            "list_fetched_at": sorted({p.get("list_fetched_at") for p in prov if p.get("list_fetched_at")}),
            "detail_fetched_range": [fetched[0], fetched[-1]] if fetched else None,
            "quality": _count((r.get("quality") or {}).get("status") for r in self.records),
        }

    def summary(self) -> list[dict]:
        rows = []
        for r in self.records:
            orgs = [o["name"] for o in r.get("organizations") or [] if o.get("role") == "beneficiary"]
            people = [p["source_text"] for p in r.get("people") or [] if p.get("role") == "beneficiary"]
            q = r.get("quality") or {}
            rows.append({
                "record_id": r["record_id"],
                "title": r.get("title"),
                "beneficiary": "; ".join(orgs or people),
                "voivodeships": (r.get("region") or {}).get("voivodeships") or [],
                "contest": (r.get("funding") or {}).get("contest"),
                "quality": q.get("status"),
                "issues": len(q.get("blocking") or []) + len(q.get("warnings") or []),
            })
        return rows

    def record(self, record_id: str) -> dict | None:
        rec = self.by_id.get(record_id)
        if rec is None:
            return None
        return {"record": rec, "raw_files": self.raw_files(rec), "data_file": str(self.data_path)}


def _count(values) -> dict:
    out: dict = {}
    for v in values:
        key = v if v is not None else "(brak)"
        out[key] = out.get(key, 0) + 1
    return out


def make_handler(store: RecordStore):
    class Handler(BaseHTTPRequestHandler):
        server_version = "RadarViewer/0.2"

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
            m = re.fullmatch(rf"/api/records/({RECORD_ID_RE})", unquote(path))
            if m:
                data = store.record(m.group(1))
                return self._json(data) if data else self._json({"error": "not found"}, 404)
            self._json({"error": "not found"}, 404)

    return Handler


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data/normalized/ncbr.jsonl", help="normalized JSONL written by a connector")
    ap.add_argument("--raw-dir", default="data/raw/ncbr", help="connector's raw page cache (shown as provenance)")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args(argv)

    data = Path(args.data)
    if not data.exists():
        print(f"brak pliku {data}: najpierw uruchom `python -X utf8 -m radar.sources.ncbr`", file=sys.stderr)
        return 2
    store = RecordStore(data, Path(args.raw_dir))
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(store))
    print(f"Radar innowacji: {len(store.records)} rekordów z {data}, http://127.0.0.1:{args.port}", file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
