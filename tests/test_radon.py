import contextlib
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlparse

from radar.http import Response
from radar.sources import radon

FIXTURES = Path(__file__).parent / "fixtures" / "radon"
TODAY = date(2026, 11, 21)
NCN_UUID = "61978f6914f9235546114ca8"  # Instytut Nauk Prawnych PAN (leader) + Instytut Języka Polskiego PAN


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text("utf-8"))


class FakeApi:
    """Serves the fixture pages by endpoint and token, like the real API (page size patched to 3)."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.pages: dict[tuple[str, str | None], str] = {}
        for kind in ("projects", "institutions"):
            token = None
            for n in range(1, 10):
                p = FIXTURES / f"{kind}_{n}.json"
                if not p.exists():
                    break
                text = p.read_text("utf-8")
                self.pages[(kind, token)] = text
                token = json.loads(text)["pagination"]["token"]

    def __call__(self, url: str) -> Response:
        self.calls.append(url)
        u = urlparse(url)
        kind = u.path.rstrip("/").rsplit("/", 1)[-1]
        q = parse_qs(u.query)
        assert q["resultNumbers"] == [str(radon.PAGE_SIZE)], url
        text = self.pages[(kind, q.get("token", [None])[0])]
        return Response(url=url, status=200, text=text, fetched_at="2026-11-21T12:00:00+00:00")


def all_institutions() -> dict:
    raw = []
    for n in (1, 2, 3):
        raw += load(f"institutions_{n}.json")["results"]
    return radon.institution_index(raw)


class InstitutionTests(unittest.TestCase):
    def test_registry_entry(self):
        idx = all_institutions()
        self.assertEqual(len(idx), 7)
        pg = next(i for i in idx.values() if i["name"] == "Politechnika Gdańska")
        self.assertEqual(pg["type_hint"], "university")
        self.assertTrue(pg["is_public"])
        self.assertEqual(pg["voivodeship"], "pomorskie")
        self.assertRegex(pg["regon"], r"^\d{9}$")
        self.assertRegex(pg["nip"], r"^\d{10}$")
        pan = next(i for i in idx.values() if i["name"].startswith("Instytut Nauk Prawnych"))
        self.assertEqual(pan["type_hint"], "research_institute")
        self.assertEqual(pan["subtype"], "instytut naukowy PAN")
        self.assertTrue(pan["is_public"])

    def test_private_university(self):
        inst = radon.normalize_institution({"institutionUuid": "x", "name": "Wyższa Szkoła X",
                                            "iKindName": "Uczelnia niepubliczna", "uTypeName": "zawodowa"})
        self.assertFalse(inst["is_public"])
        self.assertEqual(inst["type_hint"], "university")


class RecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inst = all_institutions()
        cls.projects = load("projects_1.json")["results"] + load("projects_2.json")["results"]

    def project(self, uuid):
        return next(p for p in self.projects if p["projectUuid"] == uuid)

    def test_funder_keys(self):
        keys = [radon.funder_keys(p) for p in self.projects]
        self.assertEqual(keys, [["ncn"], ["ncbr"], [], ["ncbr"]])

    def test_ncn_record(self):
        rec = radon.build_record(self.project(NCN_UUID), self.inst, page_fetched_at="t", today=TODAY)
        self.assertEqual(rec["schema"], "radar.record/v1")
        self.assertEqual(rec["source"], "radon_projects")
        self.assertEqual(rec["record_id"], NCN_UUID)
        self.assertTrue(rec["title"].startswith("Wzmacnianie pozycji obywateli"))
        self.assertGreater(len(rec["text"]["abstract"]), 1000)
        self.assertEqual(rec["funding"]["operator"], "NCN")
        self.assertEqual(rec["funding"]["programme"], "OPUS")
        self.assertEqual(rec["funding"]["project_no"], "2019/35/B/HS5/04444")
        self.assertEqual(rec["funding"]["total_value"], 797777.0)
        self.assertEqual(rec["funding"]["currency"], "PLN")
        self.assertEqual(rec["period"], {"start": "2020-10-19", "end": "2023-10-18", "precision": "day",
                                         "status": "finished", "ongoing": False, "raw": "2020-10-19 – 2023-10-18"})
        self.assertEqual(rec["extra"]["category"], "nauka")
        lead = rec["organizations"][0]
        self.assertEqual(lead["role"], "beneficiary")
        self.assertEqual(lead["name"], "Instytut Nauk Prawnych Polskiej Akademii Nauk")
        self.assertTrue(lead["in_registry"])
        self.assertEqual(lead["type_hint"], "research_institute")
        self.assertEqual(lead["received_funds"], 716297.0)
        self.assertIn("sztuczna inteligencja", rec["keywords"])
        self.assertEqual(rec["quality"]["status"], "ok")
        self.assertIn("Streszczenie:", rec["text_for_llm"])
        self.assertEqual(rec["provenance"]["connector"], f"radar.sources.radon/{radon.CONNECTOR_VERSION}")

    def test_ncbr_record_with_company(self):
        raw = next(p for p in self.projects if radon.funder_keys(p) == ["ncbr"]
                   and any("Sp. z o.o." in i["institutionName"] for i in p["implementingInstitutions"]))
        rec = radon.build_record(raw, self.inst, page_fetched_at="t", today=TODAY)
        self.assertEqual(rec["extra"]["category"], "projekty")
        self.assertEqual(rec["funding"]["operator"], "NCBR")
        names = [o["name"] for o in rec["organizations"]]
        self.assertEqual(names[0], "Politechnika Gdańska")
        company = next(o for o in rec["organizations"] if "Sp. z o.o." in o["name"])
        self.assertFalse(company["in_registry"])
        self.assertEqual(company["type_hint"], "company")
        self.assertIsNone(company["regon"])
        self.assertIn("orgs_not_in_registry:1", rec["quality"]["warnings"])
        self.assertEqual(rec["region"]["voivodeships"], ["pomorskie"])

    def test_hash_ignores_last_refresh(self):
        raw = dict(self.project(NCN_UUID))
        a = radon.build_record(raw, self.inst, page_fetched_at="t", today=TODAY)["content_hash"]
        raw["lastRefresh"] = "1"
        self.assertEqual(a, radon.build_record(raw, self.inst, page_fetched_at="t", today=TODAY)["content_hash"])
        raw["projectTitlePl"] = "inny"
        self.assertNotEqual(a, radon.build_record(raw, self.inst, page_fetched_at="t", today=TODAY)["content_hash"])

    def test_short_abstract_needs_review(self):
        raw = dict(self.project(NCN_UUID), projectAbstractPl="krótko", projectAbstractEn=None)
        rec = radon.build_record(raw, self.inst, page_fetched_at=None, today=TODAY)
        self.assertEqual(rec["quality"]["status"], "needs_review")
        self.assertIn("short_text", rec["quality"]["blocking"])

    def test_split_keywords(self):
        self.assertEqual(radon.split_keywords("a, b; a\nc."), ["a", "b", "c"])
        self.assertEqual(radon.split_keywords(None), [])


@mock.patch.object(radon, "PAGE_SIZE", 3)
class HarvestTests(unittest.TestCase):
    def test_online_then_offline(self):
        api = FakeApi()
        with tempfile.TemporaryDirectory() as tmp:
            store = radon.RawStore(Path(tmp))
            stats = radon.HarvestStats()
            recs = list(radon.harvest(store, fetcher=api, delay=0, today=TODAY, stats=stats))
            self.assertEqual(len(api.calls), 5)  # 3 institution pages + 2 project pages
            self.assertIn("token=", api.calls[1])
            self.assertEqual(stats.institutions, 7)
            self.assertEqual(stats.projects_seen, 4)
            self.assertEqual(stats.skipped_funder, 1)  # NAWA
            self.assertEqual([r["funding"]["operator"] for r in recs], ["NCN", "NCBR", "NCBR"])
            self.assertTrue(stats.complete)
            man = store.manifest("projects")
            self.assertTrue(man["complete"])
            self.assertEqual(len(man["pages"]), 2)

            offline = list(radon.harvest(store, fetcher=None, offline=True, today=TODAY))
            self.assertEqual([r["content_hash"] for r in offline], [r["content_hash"] for r in recs])

    def test_funder_filter_and_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = radon.RawStore(Path(tmp))
            only_ncn = list(radon.harvest(store, fetcher=FakeApi(), funders=["ncn"], delay=0, today=TODAY))
            self.assertEqual([r["record_id"] for r in only_ncn], [NCN_UUID])
            every = list(radon.harvest(store, offline=True, funders=None, today=TODAY))
            self.assertEqual(len(every), 4)
            nawa = next(r for r in every if not r["extra"]["funder_keys"])
            self.assertEqual(nawa["funding"]["operator"], "Narodowa Agencja Wymiany Akademickiej")

    def test_limit_stops_early_and_marks_partial(self):
        api = FakeApi()
        with tempfile.TemporaryDirectory() as tmp:
            store = radon.RawStore(Path(tmp))
            stats = radon.HarvestStats()
            recs = list(radon.harvest(store, fetcher=api, limit=1, delay=0, today=TODAY, stats=stats))
            self.assertEqual(len(recs), 1)
            self.assertEqual(sum("/projects" in c for c in api.calls), 1)
            self.assertFalse(stats.complete)
            self.assertFalse(store.manifest("projects")["complete"])

    def test_offline_without_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                list(radon.harvest(radon.RawStore(Path(tmp)), offline=True))

    def test_main_writes_records_and_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw"
            store = radon.RawStore(raw)
            list(radon.harvest(store, fetcher=FakeApi(), delay=0, today=TODAY))
            out = Path(tmp) / "out" / "radon.jsonl"
            csv_path = Path(tmp) / "out" / "radon.csv"
            with contextlib.redirect_stderr(io.StringIO()):
                rc = radon.main(["--offline", "--raw-dir", str(raw), "--out", str(out), "--csv", str(csv_path)])
            self.assertEqual(rc, 0)
            lines = out.read_text("utf-8").splitlines()
            self.assertEqual(len(lines), 3)
            registry = (Path(tmp) / "out" / "radon_institutions.jsonl").read_text("utf-8").splitlines()
            self.assertEqual(len(registry), 7)
            self.assertIn("regon", json.loads(registry[0]))
            self.assertTrue(csv_path.read_text("utf-8-sig").startswith("record_id;project_no;title"))


if __name__ == "__main__":
    unittest.main()
