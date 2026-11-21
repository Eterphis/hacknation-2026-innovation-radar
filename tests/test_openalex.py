import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from radar import RECORD_SCHEMA
from radar.http import FetchError, Response
from radar.sources import openalex

FIXTURES = Path(__file__).parent / "fixtures" / "openalex"
PAGE1 = (FIXTURES / "works_page1.json").read_text("utf-8")
PAGE2 = (FIXTURES / "works_page2.json").read_text("utf-8")


def work(n: int, page: str = PAGE1) -> dict:
    return json.loads(page)["results"][n]


class FakeApi:
    """Serves page 1 for cursor=*, page 2 for the cursor page 1 returned."""

    def __init__(self):
        self.urls: list[str] = []
        self.next_cursor = json.loads(PAGE1)["meta"]["next_cursor"]

    def __call__(self, url: str) -> Response:
        self.urls.append(url)
        cursor = parse_qs(urlsplit(url).query)["cursor"][0]
        body = PAGE1 if cursor == "*" else PAGE2 if cursor == self.next_cursor else None
        if body is None:
            raise AssertionError(f"unexpected cursor {cursor}")
        return Response(url=url, status=200, text=body, fetched_at="2026-11-21T12:00:00+00:00")


class AbstractTest(unittest.TestCase):
    def test_reconstruct_order_and_repeated_words(self):
        index = {"ma": [1, 3], "Ala": [0], "kota,": [2], "psa.": [4]}
        self.assertEqual(openalex.abstract_from_inverted_index(index), "Ala ma kota, ma psa.")

    def test_entities_tags_and_empty(self):
        self.assertEqual(openalex.abstract_from_inverted_index({"<p>A": [0], "&amp;": [1], "B</p>": [2]}), "A & B")
        self.assertEqual(openalex.abstract_from_inverted_index(None), "")
        self.assertEqual(openalex.abstract_from_inverted_index({}), "")

    def test_fixture_abstract(self):
        text = openalex.abstract_from_inverted_index(work(0)["abstract_inverted_index"])
        self.assertTrue(text.startswith("We present a low-cost perovskite module designed for agrivoltaic"))
        self.assertIn("such a module is suitable for crops sensitive to shading & heat stress", text)
        self.assertTrue(text.endswith("at the Rzeszów test site."))


class UrlTest(unittest.TestCase):
    def test_filter_and_paging_params(self):
        f = openalex.build_filter("2026-10-01")
        self.assertEqual(f, "institutions.country_code:PL,from_publication_date:2026-10-01,has_abstract:true")
        url = openalex.page_url("*", filt=f, per_page=500)
        q = parse_qs(urlsplit(url).query)
        self.assertEqual(q["filter"], [f])
        self.assertEqual(q["cursor"], ["*"])
        self.assertEqual(q["per-page"], ["200"])
        self.assertNotIn("mailto", q)

    def test_secrets_are_redacted(self):
        url = openalex.page_url("*", filt="institutions.country_code:PL", mailto="x@example.org", api_key="SECRET")
        self.assertIn("api_key=SECRET", url)
        clean = openalex.redact(url)
        self.assertNotIn("SECRET", clean)
        self.assertNotIn("example.org", clean)
        self.assertIn("filter=institutions.country_code:PL", clean)
        self.assertEqual(openalex.redact_text(f"HTTP 429 for {url}").count("SECRET"), 0)


class BuildRecordTest(unittest.TestCase):
    def setUp(self):
        self.rec = openalex.build_record(work(0), fetched_at="2026-11-21T12:00:00+00:00", page_no=1, row=1)

    def test_core_fields(self):
        r = self.rec
        self.assertEqual(r["schema"], RECORD_SCHEMA)
        self.assertEqual(r["source"], "openalex_pl")
        self.assertEqual(r["record_id"], "W4400000001")
        self.assertEqual(r["title"], "Photovoltaic perovskite modules for agrivoltaic farms in Podkarpackie")
        self.assertEqual(r["url"], "https://doi.org/10.0000/example.2026.001")
        self.assertEqual(r["extra"]["doi"], "10.0000/example.2026.001")
        self.assertEqual(r["extra"]["category"], "nauka")
        self.assertEqual(r["record_type"], "scientific_publication")
        self.assertEqual(r["period"]["start"], "2026-10-14")
        self.assertEqual(r["quality"]["status"], "ok")
        self.assertIn("Abstrakt:", r["text_for_llm"])
        self.assertEqual(r["provenance"]["connector"], f"radar.sources.openalex/{openalex.CONNECTOR_VERSION}")
        self.assertEqual(r["provenance"]["source_row"], 1)

    def test_organizations_unique_polish_first(self):
        orgs = self.rec["organizations"]
        self.assertEqual([o["name"] for o in orgs], ["Rzeszów University of Technology", "Polish Academy of Sciences",
                                                     "Fraunhofer Institute for Solar Energy Systems"])
        self.assertEqual(orgs[0]["org_id"], "https://ror.org/00example01")
        self.assertEqual(orgs[0]["type_hint"], "university")
        self.assertEqual(orgs[2]["country"], "DE")
        self.assertEqual(orgs[2]["type_hint"], "research_institute")

    def test_people_keywords_funding(self):
        r = self.rec
        self.assertEqual([p["name"] for p in r["people"]], ["Anna Przykładowa", "Jan Testowy", "Ewa Fikcyjna"])
        self.assertTrue(r["people"][0]["corresponding"])
        self.assertEqual(r["keywords"][:3], ["Agrivoltaics", "Perovskite", "Perovskite Materials and Applications"])
        self.assertEqual(len(r["keywords"]), len({k.lower() for k in r["keywords"]}))
        self.assertIn("Energy", r["keywords"])
        self.assertEqual(r["funding"]["funders"], ["Narodowe Centrum Badań i Rozwoju"])
        self.assertEqual(r["funding"]["awards"][0]["award_id"], "LIDER/00/0000/L-00/00/NCBR/2024")

    def test_short_abstract_needs_review(self):
        r = openalex.build_record(work(1))
        self.assertEqual(r["quality"]["blocking"], ["short_text"])
        self.assertEqual(r["url"], "https://example.org/notatka")
        self.assertIsNone(r["extra"]["doi"])

    def test_hash_ignores_citation_count(self):
        w = work(0)
        changed = dict(w, cited_by_count=99, updated_date="2027-01-01")
        self.assertEqual(openalex.content_hash(w), openalex.content_hash(changed))
        self.assertNotEqual(openalex.content_hash(w), openalex.content_hash(dict(w, title="Inny")))


class HarvestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "raw"
        self.addCleanup(self.tmp.cleanup)

    def test_cursor_paging_dedup_and_offline_replay(self):
        api = FakeApi()
        sleeps: list[float] = []
        stats = openalex.HarvestStats()
        recs = list(openalex.harvest(openalex.RawStore(self.root), page_fetcher=api, since="2026-09-01",
                                     api_key="SECRET", mailto="x@example.org", sleep=sleeps.append, stats=stats))
        self.assertEqual([r["record_id"] for r in recs], ["W4400000001", "W4400000002", "W4400000003"])
        self.assertEqual(len(api.urls), 2)
        self.assertEqual(sleeps, [1.0])
        self.assertEqual(stats.duplicates, 1)
        self.assertEqual(stats.total_available, 3)
        self.assertEqual(stats.status["needs_review"], 1)
        # secrets never reach the disk
        for p in self.root.rglob("*.meta.json"):
            text = p.read_text("utf-8")
            self.assertNotIn("SECRET", text)
            self.assertNotIn("example.org", text)
        self.assertNotIn("SECRET", json.dumps(recs))
        offline = list(openalex.harvest(openalex.RawStore(self.root), offline=True))
        self.assertEqual([r["record_id"] for r in offline], [r["record_id"] for r in recs])
        self.assertEqual(offline[2]["provenance"]["source_page"], 2)

    def test_limit_stops_paging(self):
        api = FakeApi()
        recs = list(openalex.harvest(openalex.RawStore(self.root), page_fetcher=api, limit=2, sleep=lambda s: None))
        self.assertEqual(len(recs), 2)
        self.assertEqual(len(api.urls), 1)
        self.assertEqual(parse_qs(urlsplit(api.urls[0]).query)["per-page"], ["2"])

    def test_new_run_replaces_old_pages(self):
        store = openalex.RawStore(self.root)
        list(openalex.harvest(store, page_fetcher=FakeApi(), sleep=lambda s: None))
        list(openalex.harvest(store, page_fetcher=FakeApi(), limit=1, sleep=lambda s: None))
        self.assertEqual(len(list(store.pages.glob("page-*.meta.json"))), 1)

    def test_bad_select_falls_back_to_full_works(self):
        api = FakeApi()

        def picky(url):
            if "select=" in url:
                raise FetchError(f"HTTP 400 for {url}")
            return api(url)
        recs = list(openalex.harvest(openalex.RawStore(self.root), page_fetcher=picky, sleep=lambda s: None))
        self.assertEqual(len(recs), 3)
        self.assertTrue(all("select=" not in u for u in api.urls))

    def test_format_changed(self):
        bad = lambda url: Response(url=url, status=200, text='{"error": "x"}', fetched_at="t")
        with self.assertRaises(openalex.FormatChanged):
            list(openalex.harvest(openalex.RawStore(self.root), page_fetcher=bad))

    def test_main_offline_writes_jsonl_and_csv(self):
        list(openalex.harvest(openalex.RawStore(self.root), page_fetcher=FakeApi(), sleep=lambda s: None))
        out, csv_path = Path(self.tmp.name) / "oa.jsonl", Path(self.tmp.name) / "oa.csv"
        rc = openalex.main(["--offline", "--raw-dir", str(self.root), "--out", str(out), "--csv", str(csv_path)])
        self.assertEqual(rc, 0)
        lines = out.read_text("utf-8").splitlines()
        self.assertEqual(len(lines), 3)
        self.assertIn("Rzeszów University of Technology", csv_path.read_text("utf-8-sig"))

    def _main(self, fetcher, *argv, env=None):
        from unittest import mock
        out = Path(self.tmp.name) / "oa.jsonl"
        # main() uses harvest's default fetcher and sleep; patch the keyword defaults
        kw = {"page_fetcher": fetcher, "sleep": lambda s: None}
        with mock.patch.dict(openalex.harvest.__kwdefaults__, kw), mock.patch.dict("os.environ", env or {}, clear=True),                 mock.patch.object(openalex, "load_env", lambda: []), mock.patch("sys.stderr"):
            rc = openalex.main(["--raw-dir", str(self.root), "--out", str(out), *argv])
        return rc, out

    def test_rate_limit_without_records_keeps_previous_output(self):
        PREVIOUS = '{"previous": true}\n'

        def limited(url):
            raise FetchError(f"HTTP 429 for {url}")
        out = Path(self.tmp.name) / "oa.jsonl"
        out.write_text(PREVIOUS, "utf-8")
        rc, out = self._main(limited, "--limit", "1")
        self.assertEqual(rc, 0, "429 is not a failure of the source")
        self.assertEqual(out.read_text("utf-8"), PREVIOUS)
        self.assertFalse(out.with_suffix(".jsonl.tmp").exists())

    def test_rate_limit_mid_run_keeps_records_fetched_before(self):
        api = FakeApi()

        def first_page_then_429(url):
            if len(api.urls):
                raise FetchError(f"HTTP 429 for {url}")
            return api(url)
        rc, out = self._main(first_page_then_429)
        self.assertEqual(rc, 0)
        recs = [json.loads(line) for line in out.read_text("utf-8").splitlines()]
        self.assertTrue(recs)
        self.assertTrue(all(r["source"] == openalex.SOURCE for r in recs))

    def test_without_key_takes_a_small_slice(self):
        api = FakeApi()
        rc, _ = self._main(api, "--max-pages", "50")
        self.assertEqual(rc, 0)
        self.assertLessEqual(len(api.urls), openalex.NO_KEY_MAX_PAGES)
        self.assertNotIn("api_key", api.urls[0])

    def test_key_from_environment_is_used(self):
        api = FakeApi()
        rc, _ = self._main(api, env={"OPENALEX_API_KEY": "test-key"})
        self.assertEqual(rc, 0)
        self.assertIn("api_key=test-key", api.urls[0])

    def test_other_http_errors_still_fail(self):
        def broken(url):
            raise FetchError(f"HTTP 500 for {url}")
        rc, out = self._main(broken)
        self.assertEqual(rc, 2)
        self.assertFalse(out.exists())

if __name__ == "__main__":
    unittest.main()
