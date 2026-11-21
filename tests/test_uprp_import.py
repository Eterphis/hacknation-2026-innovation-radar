"""UPRP import. The fixtures are synthetic files in the shape of an e-Wyszukiwarka export (real exports
cannot be fetched automatically): one Polish CSV in Windows-1250 with `;`, one English UTF-8 CSV with `,`."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from radar.sources import uprp_import as uprp
from radar.sources.dumps import read_table
from tests.test_interreg import make_xlsx

FIXTURES = Path(__file__).parent / "fixtures" / "uprp"
PL_CSV = FIXTURES / "eksport_ewyszukiwarka.csv"
EN_CSV = FIXTURES / "export_en.csv"


class UprpHelpersTest(unittest.TestCase):
    def test_numbers_and_dates(self):
        self.assertEqual(uprp.normalize_number("P.444 555"), "P.444555")
        self.assertEqual(uprp.normalize_number("PL W-130777"), "W.130777")
        self.assertEqual(uprp.parse_date("17.05.2023").isoformat(), "2023-05-17")
        self.assertEqual(uprp.parse_date("2024-02-01").isoformat(), "2024-02-01")
        self.assertEqual(uprp.parse_date("45000").isoformat(), "2023-03-15")
        self.assertIsNone(uprp.parse_date("31.02.2023"))

    def test_parties(self):
        self.assertEqual(uprp.strip_location("POLITECHNIKA RZESZOWSKA, Rzeszów, PL"), ("POLITECHNIKA RZESZOWSKA", "Rzeszów", "PL"))
        self.assertEqual(uprp.strip_location("Uniwersytet Rzeszowski (PL)"), ("Uniwersytet Rzeszowski", None, "PL"))
        self.assertTrue(uprp.is_organization("FIRMA TESTOWA SP. Z O.O."))
        self.assertTrue(uprp.is_organization("POLITECHNIKA RZESZOWSKA IM. IGNACEGO ŁUKASIEWICZA"))
        self.assertFalse(uprp.is_organization("KOWALSKI JAN"))


class UprpImportTest(unittest.TestCase):
    def test_polish_csv_cp1250(self):
        stats = uprp.HarvestStats()
        recs = list(uprp.harvest(None, files=[PL_CSV], stats=stats))
        self.assertEqual(stats.rows, 4)
        self.assertEqual(stats.duplicates, 1)
        by_id = {r["record_id"]: r for r in recs}
        r = by_id["pl-p-444555"]
        self.assertEqual(r["schema"], "radar.record/v1")
        self.assertEqual(r["title"], "Sposób wytwarzania kompozytu wodorowego")
        self.assertEqual(r["patent"]["right_number"], "PL245001")
        self.assertEqual(r["patent"]["filing_date"], "2023-05-17")
        self.assertTrue(r["patent"]["granted"])
        self.assertEqual(r["patent"]["ipc"], ["C01B 3/00", "H01M 8/04"])
        self.assertEqual(r["organizations"][0]["name"], "POLITECHNIKA RZESZOWSKA IM. IGNACEGO ŁUKASIEWICZA")
        self.assertEqual(r["organizations"][0]["location"]["city"], "Rzeszów")
        self.assertEqual(r["organizations"][0]["type_hint"], "university")
        self.assertEqual([p["name"] for p in r["people"]], ["Jan Kowalski", "Anna Nowak"])
        self.assertEqual(r["extra"], {"category": "nauka", "raw_columns": {"Uwagi": "przykład"}})
        self.assertIn("no_abstract_in_export", r["quality"]["warnings"])
        w = by_id["pl-w-130777"]
        self.assertEqual(w["record_type"], "utility_model_application")
        self.assertEqual(w["organizations"], [])  # a person as applicant
        self.assertEqual(w["people"][0]["role"], "applicant")
        self.assertEqual(w["period"]["status"], "pending_or_unknown")
        bad = next(r for r in recs if r["title"] == "Bez numeru")
        self.assertEqual(bad["quality"]["status"], "needs_review")
        self.assertIn("missing_number", bad["quality"]["blocking"])
        json.dumps(recs, ensure_ascii=False)

    def test_english_csv_and_xlsx_and_folder(self):
        rows = read_table(EN_CSV)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "import"
            folder.mkdir()
            (folder / "eksport.xlsx").write_bytes(make_xlsx(rows))
            shutil.copy(PL_CSV, folder / "starszy.csv")
            (folder / "~$eksport.xlsx").write_bytes(b"lock")
            import os
            os.utime(folder / "starszy.csv", (1_600_000_000, 1_600_000_000))
            store = uprp.RawStore(Path(tmp) / "raw")
            stats = uprp.HarvestStats()
            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("no network")):
                recs = list(uprp.harvest(store, import_dir=folder, stats=stats))
            self.assertEqual([Path(f["path"]).name for f in stats.files], ["eksport.xlsx", "starszy.csv"])
            r = recs[0]
            self.assertEqual(r["record_id"], "pl-p-450001")
            self.assertIn("photovoltaic", r["text"]["abstract"])
            self.assertEqual(r["organizations"][0]["name"], "Uniwersytet Rzeszowski")
            self.assertEqual(r["quality"]["status"], "ok")
            manifest = json.loads((Path(tmp) / "raw" / "import.meta.json").read_text("utf-8"))
            self.assertEqual(len(manifest["files"]), 2)
            self.assertEqual(len(list(uprp.harvest(None, import_dir=folder, limit=2))), 2)

    def test_empty_folder_and_bad_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                list(uprp.harvest(None, import_dir=Path(tmp)))
            p = Path(tmp) / "x.csv"
            p.write_text("a;b\n1;2\n", "utf-8")
            with self.assertRaises(uprp.FormatChanged):
                list(uprp.harvest(None, files=[p]))

    def test_main_writes_jsonl_and_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, csv_out = Path(tmp) / "uprp.jsonl", Path(tmp) / "uprp.csv"
            rc = uprp.main(["--file", str(PL_CSV), "--out", str(out), "--csv", str(csv_out), "--raw-dir", str(Path(tmp) / "raw")])
            self.assertEqual(rc, 0)
            self.assertEqual(len(out.read_text("utf-8").splitlines()), 3)
            self.assertIn("record_id;title", csv_out.read_text("utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
