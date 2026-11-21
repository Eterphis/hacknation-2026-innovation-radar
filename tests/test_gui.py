import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from radar.gui.__main__ import RecordStore, make_handler
from tests.test_card import czujnik_record


class ViewerServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.rec = czujnik_record()
        broken = dict(self.rec, record_id="toucan-eye", url="https://www.gov.pl/web/ncbr/toucan-eye",
                      quality={"status": "needs_review", "blocking": ["detail_fetch_failed: broken link"], "warnings": []})
        data = root / "ncbr.jsonl"
        data.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in (self.rec, broken)) + "\n", "utf-8")
        (root / "raw").mkdir()
        (root / "raw" / "list.html").write_text("<html></html>", "utf-8")
        self.store = RecordStore(data, root / "raw")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.store))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def get_json(self, path):
        with urllib.request.urlopen(self.base + path) as r:
            return json.loads(r.read())

    def test_index(self):
        with urllib.request.urlopen(self.base + "/") as r:
            self.assertIn("wczytane dane", r.read().decode("utf-8"))

    def test_meta_describes_loaded_file(self):
        meta = self.get_json("/api/meta")
        self.assertEqual(meta["records"], 2)
        self.assertEqual(meta["quality"], {"ok": 1, "needs_review": 1})
        self.assertIn("NCBR – Wyszukiwarka sukcesów beneficjentów", meta["sources"])
        self.assertTrue(meta["file"].endswith("ncbr.jsonl"))

    def test_list_rows(self):
        rows = self.get_json("/api/records")
        self.assertEqual([r["quality"] for r in rows], ["ok", "needs_review"])
        self.assertEqual(rows[0]["beneficiary"], "Polskie Centrum Fotoniki i Światłowodów")
        self.assertEqual(rows[0]["voivodeships"], ["lubelskie"])

    def test_record_is_returned_unchanged_with_provenance(self):
        data = self.get_json(f"/api/records/{self.rec['record_id']}")
        self.assertEqual(data["record"], self.rec)  # exactly what the connector wrote
        self.assertTrue(data["raw_files"]["list_page"]["exists"])
        self.assertFalse(data["raw_files"]["detail_page"]["exists"])
        self.assertIn("detail", data["raw_files"]["detail_page"]["path"])

    def test_not_found_and_traversal(self):
        for path in ("/api/records/nie-ma-takiego", "/api/records/..%2F..%2Fetc", "/../../etc/passwd"):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(self.base + path)
            self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
