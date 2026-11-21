"""FE 2021–2027 list. Fixture: title row, header row and 4 real rows of the dane.gov.pl file (1 Nov 2026)."""

import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from radar.http import Response
from radar.sources import fe_projects as fe

FIXTURE = Path(__file__).parent / "fixtures" / "fe" / "Lista_projektow_FE_2021_2027_sample.xlsx"
TODAY = date(2026, 11, 21)
API = {"data": [
    {"id": "100", "attributes": {"title": "Lista – 1 sierpnia 2026", "format": "xlsx", "data_date": "2026-08-01",
                                 "download_url": "https://api.dane.gov.pl/resources/100,old/file"}},
    {"id": "200", "attributes": {"title": "Lista – 1 listopada 2026", "format": "xlsx", "data_date": "2026-11-02",
                                 "download_url": "https://api.dane.gov.pl/resources/200,new/file"}},
    {"id": "300", "attributes": {"title": "Opis", "format": "pdf", "data_date": "2026-12-01",
                                 "download_url": "https://api.dane.gov.pl/resources/300/file"}},
]}


class FeHelpersTest(unittest.TestCase):
    def test_newest_xlsx(self):
        self.assertEqual(fe.newest_xlsx(API)["id"], "200")
        self.assertIsNone(fe.newest_xlsx({"data": []}))

    def test_location(self):
        loc = fe.parse_location("WOJ.: LUBELSKIE, POW.: Biała Podlaska, GM.: Biała Podlaska | WOJ.: PODLASKIE, POW.: Białystok, GM.: Białystok")
        self.assertEqual(loc["voivodeships"], ["lubelskie", "podlaskie"])
        self.assertEqual(loc["powiaty"], ["Biała Podlaska", "Białystok"])
        self.assertFalse(loc["nationwide"])
        self.assertTrue(fe.parse_location("Cały Kraj")["nationwide"])

    def test_dates(self):
        self.assertEqual(fe.parse_date("45566.083333333336").isoformat(), "2024-10-01")
        self.assertEqual(fe.parse_date("01.10.2024").isoformat(), "2024-10-01")
        self.assertIsNone(fe.parse_date("brak"))


class FeHarvestTest(unittest.TestCase):
    def records(self, **kw):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "import"
            folder.mkdir()
            shutil.copy(FIXTURE, folder / FIXTURE.name)
            stats = fe.HarvestStats()
            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("no network")):
                recs = list(fe.harvest(fe.RawStore(Path(tmp) / "raw"), use_import=True, import_dir=folder,
                                       today=TODAY, stats=stats, **kw))
            return recs, stats

    def test_import_mode(self):
        recs, stats = self.records()
        self.assertEqual(stats.rows, 4)
        self.assertEqual(len(recs), 4)
        r = next(r for r in recs if r["funding"]["project_no"] == "FENX.02.04-IW.01-0063/25")
        self.assertEqual(r["schema"], "radar.record/v1")
        self.assertEqual(r["record_id"], "fenx-02-04-iw-01-0063-25")
        self.assertTrue(r["title"].startswith("Budowa zbiornika retencyjnego"))
        self.assertEqual(r["organizations"][0]["name"], "Gmina Sokółka")
        self.assertEqual(r["organizations"][0]["type_hint"], "local_government")
        self.assertEqual(r["region"]["voivodeships"], ["podlaskie"])
        self.assertEqual(r["region"]["gminy"], ["Sokółka"])
        self.assertEqual(r["funding"]["fund"], "EFRR")
        self.assertEqual(r["funding"]["total_value"], 20000000.0)
        self.assertEqual(r["funding"]["currency"], "PLN")
        self.assertIsInstance(r["funding"]["grant_share"], float)
        self.assertLess(r["funding"]["grant_share"], 1)
        self.assertIsNotNone(r["period"]["start"])
        self.assertEqual(r["extra"]["category"], "projekty")
        self.assertEqual(r["quality"]["status"], "ok")
        self.assertIsNone(r["provenance"]["source_file_url"])
        nationwide = next(r for r in recs if r["funding"]["project_no"] == "FAMI.01.01-IZ.00-0002/24")
        self.assertTrue(nationwide["region"]["nationwide"])
        short = next(r for r in recs if r["funding"]["project_no"] == "FEWP.08.01-IZ.00-0127/24")
        self.assertIn("short_text", short["quality"]["blocking"])
        json.dumps(recs, ensure_ascii=False)
        self.assertEqual(len(self.records(limit=2)[0]), 2)

    def test_online_via_api_then_offline(self):
        calls = []

        def api_fetcher(url, accept=""):
            calls.append(url)
            return Response(url, 200, json.dumps(API), "2026-11-21T12:00:00+00:00")

        def downloader(url, dest, **kw):
            calls.append(url)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(FIXTURE, dest)
            meta = {"url": url, "fetched_at": "2026-11-21T12:00:01+00:00", "etag": '"x"', "bytes": dest.stat().st_size,
                    "path": dest.name}
            dest.with_name(dest.name + ".meta.json").write_text(json.dumps(meta), "utf-8")
            return {**meta, "path": str(dest), "changed": True}

        with tempfile.TemporaryDirectory() as tmp:
            store = fe.RawStore(Path(tmp))
            recs = list(fe.harvest(store, api_fetcher=api_fetcher, downloader=downloader, today=TODAY))
            self.assertEqual(calls, [fe.RESOURCES_API, "https://api.dane.gov.pl/resources/200,new/file"])
            self.assertEqual(len(recs), 4)
            self.assertEqual(recs[0]["provenance"]["source_file_url"], "https://api.dane.gov.pl/resources/200,new/file")
            self.assertEqual(recs[0]["rights"]["licence"], "CC0 1.0")
            offline = list(fe.harvest(store, offline=True, today=TODAY))
            self.assertEqual([r["content_hash"] for r in offline], [r["content_hash"] for r in recs])

    def test_missing_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                list(fe.harvest(fe.RawStore(Path(tmp)), offline=True))
            with self.assertRaises(FileNotFoundError):
                list(fe.harvest(fe.RawStore(Path(tmp)), use_import=True, import_dir=Path(tmp) / "none"))
            bad = Path(tmp) / "x.csv"
            bad.write_text("a;b\n1;2\n", "utf-8")
            with self.assertRaises(fe.FormatChanged):
                list(fe.harvest(fe.RawStore(Path(tmp)), use_import=True, import_dir=Path(tmp)))


if __name__ == "__main__":
    unittest.main()
