import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from radar import store as db
from radar.gui.__main__ import DbRecordStore, RecordStore, make_handler
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
        self.store = RecordStore([data], root / "raw")
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
        self.assertTrue(meta["files"][0]["path"].endswith("ncbr.jsonl"))

    def test_list_rows(self):
        rows = self.get_json("/api/records")
        self.assertEqual([r["quality"] for r in rows], ["ok", "needs_review"])
        self.assertEqual(rows[0]["beneficiary"], "Polskie Centrum Fotoniki i Światłowodów")
        self.assertEqual(rows[0]["voivodeships"], ["lubelskie"])
        self.assertEqual(rows[0]["key"], "ncbr_sukcesy/" + self.rec["record_id"])

    def test_several_sources_with_same_record_id(self):
        root = Path(self.tmp.name)
        other = dict(self.rec, source="interreg_pl", source_name="Interreg",
                     provenance={"raw_files": {"source_file": str(root / "raw" / "list.html")}, "source_file_url": "https://x/w.xlsx"})
        second = root / "interreg.jsonl"
        second.write_text(json.dumps(other, ensure_ascii=False) + "\n", "utf-8")
        store = RecordStore([self.store.data_paths[0], second], root / "raw")
        self.assertEqual(len(store.records), 3)
        both = store.record("interreg_pl/" + self.rec["record_id"])
        self.assertEqual(both["record"]["source"], "interreg_pl")
        self.assertTrue(both["raw_files"]["source_file"]["exists"])
        self.assertTrue(both["data_file"].endswith("interreg.jsonl"))

    def test_record_is_returned_unchanged_with_provenance(self):
        data = self.get_json(f"/api/records/ncbr_sukcesy/{self.rec['record_id']}")
        self.assertEqual(data["record"], self.rec)  # exactly what the connector wrote
        self.assertTrue(data["raw_files"]["list_page"]["exists"])
        self.assertFalse(data["raw_files"]["detail_page"]["exists"])
        self.assertIn("detail", data["raw_files"]["detail_page"]["path"])

    def test_not_found_and_traversal(self):
        for path in ("/api/records/ncbr_sukcesy/nie-ma-takiego", "/api/records/..%2F..%2Fetc", "/api/records/toucan-eye", "/../../etc/passwd"):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(self.base + path)
            self.assertEqual(ctx.exception.code, 404)


class DbViewerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.rec = czujnik_record()
        other = dict(self.rec, record_id="inny", title="Pompa ciepła", content_hash="x",
                     text_for_llm="Tytuł: Pompa ciepła", organizations=[], keywords=[])
        self.db_path = root / "radar.db"
        conn = db.connect(self.db_path)
        db.upsert_source(conn, self.rec["source"], [self.rec, other], "2026-11-01T00:00:00+00:00")
        db.add_refresh_run(conn, "ncbr", {"ok": True, "at": "2026-11-01T00:00:00+00:00", "rebuild": "rebuilt"})
        conn.close()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(DbRecordStore(self.db_path, root / "raw")))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def get_json(self, path):
        with urllib.request.urlopen(self.base + path) as r:
            return json.loads(r.read())

    def test_meta_from_db(self):
        meta = self.get_json("/api/meta")
        self.assertEqual(meta["records"], 2)
        self.assertEqual(meta["db"], str(self.db_path))
        self.assertEqual(meta["refresh_runs"][0]["source"], "ncbr")

    def test_full_text_search(self):
        keys = [r["key"] for r in self.get_json("/api/records?q=odksztalcen")]
        self.assertEqual(keys, ["ncbr_sukcesy/" + self.rec["record_id"]])
        self.assertEqual(len(self.get_json("/api/records")), 2)
        self.assertEqual(len(self.get_json("/api/records?q=pompa%20ciepla")), 1)

    def test_record_with_history(self):
        data = self.get_json(f"/api/records/ncbr_sukcesy/{self.rec['record_id']}")
        self.assertEqual(data["record"], self.rec)
        self.assertEqual(data["history"]["first_seen"], "2026-11-01T00:00:00+00:00")
        self.assertEqual(len(data["history"]["versions"]), 1)

    def test_categories_in_meta_and_filter(self):
        conn = db.connect(self.db_path)
        conn.execute("UPDATE records SET category='projekty' WHERE record_id=?", (self.rec["record_id"],))
        conn.commit()
        conn.close()
        meta = self.get_json("/api/meta")
        self.assertEqual(meta["categories"], {"projekty": 1, "(brak)": 1})
        rows = self.get_json("/api/records?category=projekty")
        self.assertEqual([r["category"] for r in rows], ["projekty"])

    def test_paged_list_with_filters(self):
        page = self.get_json("/api/records?limit=1&offset=0")
        self.assertEqual((page["total"], page["limit"], len(page["rows"])), (2, 1, 1))
        second = self.get_json("/api/records?limit=1&offset=1")
        self.assertNotEqual(page["rows"][0]["key"], second["rows"][0]["key"])
        hit = self.get_json("/api/records?limit=50&q=odksztalcen")
        self.assertEqual(hit["total"], 1)
        none = self.get_json("/api/records?limit=50&category=-")
        self.assertEqual(none["total"], 2)  # no category set in this fixture
        meta = self.get_json("/api/meta")
        self.assertIn("voivodeships", meta)
        self.assertTrue(meta["first_seen_min"])
        light = self.get_json("/api/meta?light=1")
        self.assertEqual((light["records"], light["refresh_runs"][0]["source"]), (2, "ncbr"))
        self.assertNotIn("sources", light)

    def test_viewer_reads_while_a_writer_holds_the_lock(self):
        import sqlite3, time
        writer = sqlite3.connect(self.db_path, timeout=1)
        writer.execute("BEGIN IMMEDIATE")  # a harvest in the middle of a transaction
        writer.execute("UPDATE records SET title=title")
        try:
            start = time.monotonic()
            self.assertEqual(self.get_json("/api/meta")["records"], 2)
            self.assertEqual(self.get_json("/api/records?limit=10")["total"], 2)
            self.assertLess(time.monotonic() - start, 2.0)
        finally:
            writer.rollback()
            writer.close()

    def test_new_data_visible_without_restart(self):
        conn = db.connect(self.db_path)
        db.upsert_source(conn, self.rec["source"], [self.rec])
        conn.close()
        self.assertEqual(len(self.get_json("/api/records")), 1)
        self.assertEqual(len(self.get_json("/api/records?removed=1")), 2)


if __name__ == "__main__":
    unittest.main()
