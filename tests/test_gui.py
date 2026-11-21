import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from radar.card import build_card
from radar.gui.__main__ import Store, make_handler
from radar.llm import RulesExtractor
from tests.test_card import czujnik_record


class GuiServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.card = build_card(czujnik_record(), [RulesExtractor()])
        (root / "cards.jsonl").write_text(json.dumps(self.card, ensure_ascii=False) + "\n", "utf-8")
        self.decisions = root / "decisions.jsonl"
        self.store = Store(root / "cards.jsonl", self.decisions)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.store))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def get(self, path):
        with urllib.request.urlopen(self.base + path) as r:
            return r.status, r.read().decode("utf-8")

    def post(self, path, body: bytes):
        req = urllib.request.Request(self.base + path, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_index_and_list(self):
        status, html = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("Radar innowacji", html)
        _, body = self.get("/api/cards")
        rows = json.loads(body)
        self.assertEqual(rows[0]["card_id"], self.card["card_id"])
        self.assertEqual(rows[0]["level"], "tech_ready")
        self.assertIsNone(rows[0]["decision"])

    def test_card_detail_has_markdown(self):
        _, body = self.get(f"/api/cards/{self.card['card_id']}")
        data = json.loads(body)
        self.assertIn("## 5. Rozstrzygnięcie", data["markdown"])

    def test_decision_roundtrip_and_persistence(self):
        cid = self.card["card_id"]
        status, entry = self.post(f"/api/cards/{cid}/decision",
                                  json.dumps({"decision": "approve", "note": "do CTT"}).encode("utf-8"))
        self.assertEqual((status, entry["decision"]), (200, "approve"))
        self.assertEqual(json.loads(self.get("/api/cards")[1])[0]["decision"], "approve")
        # a fresh store reads the log back: decisions survive a restart
        self.assertEqual(Store(self.store.cards_path, self.decisions).decisions[cid]["note"], "do CTT")
        self.post(f"/api/cards/{cid}/decision", b'{"decision": "reset"}')
        self.assertNotIn(cid, Store(self.store.cards_path, self.decisions).decisions)
        self.assertEqual(len(self.decisions.read_text("utf-8").splitlines()), 2)  # append-only log

    def test_bad_requests(self):
        cid = self.card["card_id"]
        self.assertEqual(self.post(f"/api/cards/{cid}/decision", b'{"decision": "maybe"}')[0], 400)
        self.assertEqual(self.post(f"/api/cards/{cid}/decision", b"\xff\xfe not json")[0], 400)
        self.assertEqual(self.post("/api/cards/K-00000000/decision", b'{"decision": "approve"}')[0], 404)
        with self.assertRaises(urllib.error.HTTPError):
            self.get("/../../etc/passwd")


if __name__ == "__main__":
    unittest.main()
