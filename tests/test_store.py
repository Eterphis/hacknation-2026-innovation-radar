import json
import tempfile
import unittest
from pathlib import Path

from radar import store
from tests.test_card import czujnik_record


def variant(rec, **changes):
    out = json.loads(json.dumps(rec))
    out.update(changes)
    return out


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.conn = store.connect(self.root / "radar.db")
        self.rec = czujnik_record()
        self.src = self.rec["source"]
        self.other = variant(self.rec, record_id="inny-projekt", title="Inny projekt o wodzie", content_hash="h2",
                             text_for_llm="Tytuł: Inny projekt o wodzie", keywords=[])

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_schema_version_and_reopen(self):
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], len(store.MIGRATIONS))
        again = store.connect(self.root / "radar.db")  # migrations are idempotent
        self.assertEqual(again.execute("PRAGMA user_version").fetchone()[0], len(store.MIGRATIONS))
        again.close()

    def test_add_unchanged_changed_removed_restored(self):
        c = store.upsert_source(self.conn, self.src, [self.rec, self.other], "2026-01-01T00:00:00+00:00")
        self.assertEqual((c["added"], c["changed"], c["removed"]), (2, 0, 0))

        c = store.upsert_source(self.conn, self.src, [self.rec, self.other], "2026-01-02T00:00:00+00:00")
        self.assertEqual((c["added"], c["unchanged"]), (0, 2))

        changed = variant(self.rec, title="Nowy tytuł", content_hash="nowy")
        c = store.upsert_source(self.conn, self.src, [changed], "2026-01-03T00:00:00+00:00")
        self.assertEqual((c["changed"], c["removed"]), (1, 1))
        got = store.get_record(self.conn, self.src, self.rec["record_id"])
        self.assertEqual(got["record"]["title"], "Nowy tytuł")
        self.assertEqual(got["history"]["first_seen"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(got["history"]["changed_at"], "2026-01-03T00:00:00+00:00")
        self.assertEqual(len(got["history"]["versions"]), 2)
        gone = store.get_record(self.conn, self.src, "inny-projekt")
        self.assertEqual(gone["history"]["removed_at"], "2026-01-03T00:00:00+00:00")
        self.assertEqual(len(store.list_records(self.conn)), 1)
        self.assertEqual(len(store.list_records(self.conn, include_removed=True)), 2)

        c = store.upsert_source(self.conn, self.src, [changed, self.other], "2026-01-04T00:00:00+00:00")
        self.assertEqual(c["restored"], 1)
        self.assertIsNone(store.get_record(self.conn, self.src, "inny-projekt")["history"]["removed_at"])

    def test_same_record_id_in_two_sources(self):
        store.upsert_source(self.conn, self.src, [self.rec])
        store.upsert_source(self.conn, "interreg_pl", [variant(self.rec, source="interreg_pl")])
        self.assertEqual(store.stats(self.conn)["records"], 2)

    def test_wrong_source_is_rejected(self):
        with self.assertRaises(ValueError):
            store.upsert_source(self.conn, "interreg_pl", [self.rec])

    def test_search_without_polish_letters(self):
        store.upsert_source(self.conn, self.src, [self.rec, self.other])
        for q in ("odksztalcen", "ODKSZTAŁCEŃ", "czujnik odksztalcen"):
            ids = [r["record_id"] for r in store.list_records(self.conn, q=q)]
            self.assertEqual(ids, [self.rec["record_id"]], q)
        self.assertEqual(store.list_records(self.conn, q="nie-ma-takiego-slowa"), [])

    def test_filters(self):
        store.upsert_source(self.conn, self.src, [self.rec, variant(self.other, region={"voivodeships": ["mazowieckie"]})])
        self.assertEqual(len(store.list_records(self.conn, voivodeship="lubelskie")), 1)
        self.assertEqual(len(store.list_records(self.conn, quality="ok", source=self.src)), 2)

    def test_export_roundtrip_and_import(self):
        path = self.root / "in.jsonl"
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in (self.rec, self.other)) + "\n", "utf-8")
        counts = store.import_jsonl(self.conn, path)
        self.assertEqual(counts[self.src]["added"], 2)
        out = self.root / "out.jsonl"
        self.assertEqual(store.export_jsonl(self.conn, out), 2)
        self.assertEqual(store.read_jsonl(out), [self.rec, self.other])

    def test_organizations_are_shared(self):
        store.upsert_source(self.conn, self.src, [self.rec, self.other])
        self.assertEqual(store.stats(self.conn)["organizations"], 1)  # same beneficiary in both

    def test_stale_records_for_cards(self):
        store.upsert_source(self.conn, self.src, [self.rec, self.other])
        self.assertEqual(len(store.stale_records(self.conn)), 2)
        store.save_card(self.conn, {"card_id": "k1", "status": "ok", "scores": {"total": 3}}, self.rec)
        self.assertEqual([r["record_id"] for r in store.stale_records(self.conn)], ["inny-projekt"])
        store.upsert_source(self.conn, self.src, [variant(self.rec, content_hash="zmiana"), self.other])
        self.assertEqual(len(store.stale_records(self.conn)), 2)

    def test_refresh_runs(self):
        store.add_refresh_run(self.conn, "ncbr", {"ok": True, "at": "t1", "rebuild": "rebuilt", "input_sha256": "a"})
        store.add_refresh_run(self.conn, "ncbr", {"ok": False, "at": "t2", "error": "x"})
        self.assertEqual(store.last_successful_run(self.conn, "ncbr")["input_sha256"], "a")
        self.assertEqual(store.last_successful_run(self.conn, "interreg"), {})
        self.assertEqual([r["at"] for r in store.refresh_runs(self.conn)], ["t2", "t1"])

    def test_removal_guard_and_force(self):
        third = variant(self.rec, record_id="trzeci", content_hash="h3")
        store.upsert_source(self.conn, self.src, [self.rec, self.other, third])
        c = store.upsert_source(self.conn, self.src, [self.rec])  # 2 of 3 would vanish: suspicious harvest
        self.assertEqual((c["removed"], c["removal_skipped"]), (0, 2))
        self.assertEqual(store.stats(self.conn)["records"], 3)
        c = store.upsert_source(self.conn, self.src, [self.rec], force_removal=True)
        self.assertEqual((c["removed"], c["removal_skipped"]), (2, 0))
        c = store.upsert_source(self.conn, self.src, [self.rec, self.other, third])
        self.assertEqual(c["restored"], 2)
        c = store.upsert_source(self.conn, self.src, [self.rec, self.other])  # 1 of 3 is within the guard
        self.assertEqual((c["removed"], c["removal_skipped"]), (1, 0))

    def test_mark_removed_and_category(self):
        store.upsert_source(self.conn, self.src, [self.rec, self.other], category="projekty")
        self.assertEqual(store.mark_removed(self.conn, self.src, ["inny-projekt"]), 1)
        self.assertEqual(store.mark_removed(self.conn, self.src, ["inny-projekt"]), 0)  # already gone
        self.assertEqual([r["record_id"] for r in store.list_records(self.conn, category="projekty")],
                         [self.rec["record_id"]])
        self.assertEqual(store.list_records(self.conn, category="nauka"), [])
        self.assertEqual(store.stats(self.conn)["categories"], {"projekty": 1})


class ChunkedWriteTest(unittest.TestCase):
    def test_large_harvest_is_visible_to_readers_while_it_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "radar.db"
            conn = store.connect(path)
            base = czujnik_record()
            seen_by_reader = []

            def records():
                for i in range(12):
                    if i == 7:  # after the first chunk of 5 was committed
                        reader = store.connect_readonly(path)
                        seen_by_reader.append(reader.execute("SELECT COUNT(*) FROM records").fetchone()[0])
                        reader.close()
                    yield variant(base, record_id=f"r{i}", content_hash=f"h{i}")

            c = store.upsert_source(conn, base["source"], records(), chunk=5)
            self.assertEqual(c["added"], 12)
            self.assertEqual(seen_by_reader, [5])
            ro = store.connect_readonly(path)
            with self.assertRaises(Exception):
                ro.execute("DELETE FROM records")  # the viewer's connection cannot write
            ro.close()
            conn.close()


class MigrationTest(unittest.TestCase):
    def test_v1_database_is_upgraded(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.db"
            old = sqlite3.connect(path)
            old.executescript(store.MIGRATIONS[0])
            old.execute("PRAGMA user_version=1")
            old.execute("INSERT INTO records(source, record_id, title, first_seen, last_seen, changed_at, data) "
                        "VALUES ('ncbr_sukcesy', 'a', 'Stary', 't', 't', 't', '{}')")
            old.commit()
            old.close()
            conn = store.connect(path)
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], len(store.MIGRATIONS))
            cols = {r[1] for r in conn.execute("PRAGMA table_info(records)")}
            self.assertIn("category", cols)
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({"crawl_sites", "crawl_pages"} <= tables)
            self.assertEqual(conn.execute("SELECT title, category FROM records").fetchone()[:], ("Stary", None))
            conn.close()


if __name__ == "__main__":
    unittest.main()
