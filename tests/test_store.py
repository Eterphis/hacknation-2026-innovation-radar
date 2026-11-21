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


if __name__ == "__main__":
    unittest.main()
