"""Radar innowacji – local operator UI (standard library only).

Run:  python -X utf8 -m radar.gui            -> http://127.0.0.1:8765
      python -X utf8 -m radar.gui --rebuild  (rebuild cards from data/normalized first)

Decisions are appended to data/decisions.jsonl (append-only log; the latest entry per card wins).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..card import build_card, render_justification
from ..llm import get_providers

STATIC = Path(__file__).parent / "static"
DECISIONS = {"approve", "reject", "reset"}


class Store:
    """Cards in memory plus the decision log on disk."""

    def __init__(self, cards_path: Path, decisions_path: Path) -> None:
        self.cards_path = cards_path
        self.decisions_path = decisions_path
        self.lock = threading.Lock()
        self.cards: dict[str, dict] = {}
        self.order: list[str] = []
        self.decisions: dict[str, dict] = {}
        self.reload()

    def reload(self) -> None:
        cards = [json.loads(line) for line in self.cards_path.read_text("utf-8").splitlines() if line.strip()]
        self.cards = {c["card_id"]: c for c in cards}
        self.order = [c["card_id"] for c in cards]
        self.decisions = {}
        if self.decisions_path.exists():
            for line in self.decisions_path.read_text("utf-8").splitlines():
                if line.strip():
                    d = json.loads(line)
                    if d["decision"] == "reset":
                        self.decisions.pop(d["card_id"], None)
                    else:
                        self.decisions[d["card_id"]] = d

    def summary(self) -> list[dict]:
        out = []
        for cid in self.order:
            c = self.cards[cid]
            sc, mat, rt, facts = c.get("scores", {}), c.get("maturity", {}), c.get("route", {}), c.get("facts", {})
            orgs = [o["name"] for o in facts.get("organizations", []) if o.get("role") == "beneficiary"]
            if not orgs:
                orgs = [p["source_text"] for p in facts.get("people", [])]
            out.append({
                "card_id": cid,
                "title": c.get("title"),
                "status": c.get("status"),
                "total": sc.get("total"),
                "light": sc.get("light"),
                "level": mat.get("level"),
                "level_index": mat.get("level_index"),
                "hidden": mat.get("hidden", False),
                "path": rt.get("path"),
                "pci": rt.get("pci_priority_sectors", []),
                "recipient_types": sorted({r["recipient_type"] for r in rt.get("recipients", [])}),
                "innovation_type": c.get("extraction", {}).get("innovation_type"),
                "org": "; ".join(orgs),
                "voivodeships": (facts.get("region") or {}).get("voivodeships", []),
                "decision": (self.decisions.get(cid) or {}).get("decision"),
            })
        return out

    def card(self, cid: str) -> dict | None:
        c = self.cards.get(cid)
        if c is None:
            return None
        return {"card": c, "markdown": render_justification(c), "decision": self.decisions.get(cid)}

    def decide(self, cid: str, decision: str, note: str) -> dict:
        entry = {"card_id": cid, "record_id": self.cards[cid]["record_id"], "decision": decision,
                 "note": note[:2000], "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        with self.lock:
            self.decisions_path.parent.mkdir(parents=True, exist_ok=True)
            with self.decisions_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            if decision == "reset":
                self.decisions.pop(cid, None)
            else:
                self.decisions[cid] = entry
        return entry


def make_handler(store: Store):
    class Handler(BaseHTTPRequestHandler):
        server_version = "RadarGUI/0.1"

        def log_message(self, fmt, *args):  # quieter console
            if not self.path.startswith("/api/cards/"):
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
            if path == "/api/cards":
                return self._json(store.summary())
            m = re.fullmatch(r"/api/cards/(K-[0-9A-F]{8})", path)
            if m:
                data = store.card(m.group(1))
                return self._json(data) if data else self._json({"error": "not found"}, 404)
            self._json({"error": "not found"}, 404)

        def do_POST(self):
            m = re.fullmatch(r"/api/cards/(K-[0-9A-F]{8})/decision", self.path)
            if not m or m.group(1) not in store.cards:
                return self._json({"error": "not found"}, 404)
            try:
                length = min(int(self.headers.get("Content-Length", 0)), 10_000)
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self._json({"error": "bad json"}, HTTPStatus.BAD_REQUEST)
            decision = body.get("decision")
            if decision not in DECISIONS:
                return self._json({"error": "decision must be approve | reject | reset"}, HTTPStatus.BAD_REQUEST)
            self._json(store.decide(m.group(1), decision, str(body.get("note") or "")))

    return Handler


def rebuild_cards(normalized: Path, cards_path: Path, llm: str | None) -> None:
    records = [json.loads(line) for line in normalized.read_text("utf-8").splitlines() if line.strip()]
    records = [r for r in records if r.get("quality", {}).get("status") == "ok"]
    providers = get_providers(llm)
    print(f"building {len(records)} cards ({' -> '.join(p.name for p in providers)}) ...", file=sys.stderr)
    cards_path.parent.mkdir(parents=True, exist_ok=True)
    with cards_path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(build_card(r, providers), ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cards", default="data/cards/all/cards.jsonl")
    ap.add_argument("--normalized", default="data/normalized/ncbr.jsonl")
    ap.add_argument("--decisions", default="data/decisions.jsonl")
    ap.add_argument("--rebuild", action="store_true", help="rebuild cards from --normalized before starting")
    ap.add_argument("--llm", default=None, help="auto | claude | offline (for --rebuild)")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args(argv)

    cards_path = Path(args.cards)
    if args.rebuild or not cards_path.exists():
        normalized = Path(args.normalized)
        if not normalized.exists():
            print(f"no {normalized}: run `python -X utf8 -m radar.sources.ncbr` first", file=sys.stderr)
            return 2
        rebuild_cards(normalized, cards_path, args.llm or "offline")

    store = Store(cards_path, Path(args.decisions))
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(store))
    print(f"Radar innowacji: {len(store.cards)} kart, http://127.0.0.1:{args.port}", file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
