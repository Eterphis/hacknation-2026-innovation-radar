"""scripts/fetch_gus_adopters.py on canned BDL answers: variable picked by name, Poland + 16 voivodeships, latest
year present everywhere, ids and dates recorded. No network."""
import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("fetch_gus_adopters", Path(__file__).parents[1] / "scripts" / "fetch_gus_adopters.py")
gus = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gus)

WOJ = {f"01{code}00000000": 10 + i for i, code in enumerate(gus.VOIVODESHIPS)}  # 10..25, sum 280


class FakeBdl(gus.Bdl):
    def __init__(self):
        super().__init__(None, 0)
        self.asked = []

    def get(self, path, **params):
        self.asked.append((path, params))
        if path == "variables":
            return {"results": [
                {"id": 1, "subjectId": "P1413", "n1": "gminy miejskie"},
                {"id": 2, "subjectId": "P1413", "n1": "ogółem"},
                {"id": 3, "subjectId": "P1413", "n1": "gminy wiejskie"},
            ], "links": {}}
        level = params["unit-level"]
        if level == 0:
            return {"results": [{"id": "000000000000", "values": [{"year": "2023", "val": 279}, {"year": "2024", "val": 280}]}], "links": {}}
        units = [{"id": u, "values": [{"year": "2023", "val": v - 1}] + [{"year": "2024", "val": v}]}
                 for u, v in WOJ.items()]
        return {"results": units, "links": {}}


class FetchGusTest(unittest.TestCase):
    def test_indicator_from_canned_api(self):
        bdl = FakeBdl()
        spec = {"label": "gmin", "parts": [("P1413", [gus.TOTAL], [r"miejsk", r"wiejsk"])]}
        g = gus.fetch_indicator(bdl, "gminy", spec, verbose=False)
        self.assertEqual(g["variable_id"], 2)
        self.assertEqual(g["variable_ids"], [2])
        self.assertEqual(g["year"], 2024)
        self.assertEqual(g["poland"], 280)
        self.assertEqual(len(g["by_voivodeship"]), 16)
        self.assertEqual(g["by_voivodeship"]["podkarpackie"], WOJ["011800000000"])
        self.assertEqual(sum(g["by_voivodeship"].values()), 280)
        self.assertIn("P1413", g["source"])
        self.assertTrue(g["fetched_at"])
        self.assertIn(("variables", {"page-size": 100, "page": 0, "subject-id": "P1413"}), bdl.asked)

    def test_ambiguous_pattern_stops_with_candidates(self):
        with self.assertRaises(SystemExit) as e:
            gus.pick_variable(FakeBdl(), "gminy", "P1413", [r"gminy"], [])
        self.assertIn("2 pasujące zmienne", str(e.exception))

    def test_latest_year_must_exist_everywhere(self):
        pl = {"PL": {2023: 1, 2024: 2}}
        woj = {"a": {2023: 1, 2024: 2}, "b": {2023: 1}}
        self.assertEqual(gus.latest_full_year(pl, woj), 2023)

    def test_voivodeship_from_unit_id(self):
        self.assertEqual(gus.voivodeship_of("011200000000"), "małopolskie")
        self.assertEqual(gus.voivodeship_of("061800000000"), "podkarpackie")


if __name__ == "__main__":
    unittest.main()
