"""Biblioteka Nauki connector and the OAI-PMH client, offline.

Fixtures are real responses from https://bibliotekanauki.pl/api/oai/articles (2026-11-21), trimmed to a
few records: page1 = 2 records + resumptionToken, page2 = 1 record + 1 deleted header + empty token
(last page), page_oai_dc = 2 deleted headers + 1 record in plain Dublin Core.
"""

import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from radar import RECORD_SCHEMA
from radar.crawl import oai
from radar.http import FetchError, Response
from radar.sources import bibliotekanauki as bn

FIX = Path(__file__).parent / "fixtures" / "bibliotekanauki"
SETS = {"11": "Nauki Inżynierskie i Technologie"}


def read(name: str) -> str:
    return (FIX / name).read_text("utf-8")


def page(name: str) -> oai.Page:
    return oai.parse_response(read(name), url="https://example.test/oai", fetched_at="2026-11-21T16:50:00+00:00")


class FakeOAI:
    """Serves fixtures by OAI arguments and records every URL asked for."""

    def __init__(self, first="page1_oai_openaire.xml", fail_sets=False):
        self.first = first
        self.fail_sets = fail_sets
        self.urls: list[str] = []

    def __call__(self, url: str) -> Response:
        self.urls.append(url)
        q = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        if q["verb"] == "ListSets":
            if self.fail_sets:
                raise FetchError("HTTP 503")
            name = "sets_sample.xml"
        elif "resumptionToken" in q:
            name = "page2_oai_openaire.xml"
        else:
            name = self.first
        return Response(url=url, status=200, text=read(name), fetched_at="2026-11-21T16:50:00+00:00")


# --- OAI client ----------------------------------------------------------------------
class OAIParseTest(unittest.TestCase):
    def test_list_records_page(self):
        p = page("page1_oai_openaire.xml")
        self.assertEqual(len(p.records), 2)
        h = p.records[0].header
        self.assertEqual(h.identifier, "oai:bibliotekanauki.pl:5166")
        self.assertEqual(h.sets, ["11"])
        self.assertFalse(h.deleted)
        self.assertTrue(h.datestamp.startswith("20"))
        self.assertEqual(oai.local(p.records[0].metadata.tag), "resource")
        self.assertTrue(p.token)
        self.assertEqual(p.response_date[:4], "2026")

    def test_last_page_and_deleted(self):
        p = page("page2_oai_openaire.xml")
        self.assertIsNone(p.token)  # empty <resumptionToken/> ends the list
        deleted = [r for r in p.records if r.header.deleted]
        self.assertEqual(len(deleted), 1)
        self.assertIsNone(deleted[0].metadata)

    def test_no_records_match_is_empty(self):
        p = page("no_records_match.xml")
        self.assertEqual(p.records, [])
        self.assertEqual(p.empty_reason, "noRecordsMatch")
        self.assertIsNone(p.token)

    def test_other_errors_raise(self):
        xml = read("no_records_match.xml").replace('code="noRecordsMatch"', 'code="badResumptionToken"')
        with self.assertRaises(oai.OAIError) as cm:
            oai.parse_response(xml)
        self.assertEqual(cm.exception.code, "badResumptionToken")

    def test_not_oai(self):
        for text in ("<html><body>High Load</body></html>", "not xml at all",
                     '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><x>&a;</x>'):
            with self.assertRaises(oai.OAIError):
                oai.parse_response(text)

    def test_list_sets(self):
        p = page("sets_sample.xml")
        self.assertIn(("11", "Nauki Inżynierskie i Technologie"), p.sets)

    def test_request_url(self):
        u = oai.request_url("https://x.test/oai", "ListRecords", metadata_prefix="oai_dc", set_spec="11",
                            from_="2026-11-01")
        self.assertEqual(parse_qs(urlsplit(u).query),
                         {"verb": ["ListRecords"], "metadataPrefix": ["oai_dc"], "set": ["11"], "from": ["2026-11-01"]})
        # a resumptionToken excludes every other argument
        u = oai.request_url("https://x.test/oai", "ListRecords", resumption_token="abc.", metadata_prefix="oai_dc")
        self.assertEqual(parse_qs(urlsplit(u).query), {"verb": ["ListRecords"], "resumptionToken": ["abc."]})


class OAIPagingTest(unittest.TestCase):
    def test_follows_token_with_delay(self):
        fake, sleeps = FakeOAI(), []
        pages = list(oai.iter_pages("https://x.test/oai", metadata_prefix="oai_openaire", from_="2026-11-01",
                                    fetcher=fake, delay=2.0, sleep=sleeps.append))
        self.assertEqual(len(pages), 2)
        self.assertEqual(sleeps, [2.0])  # pause between pages, not before the first
        self.assertIn("from=2026-11-01", fake.urls[0])
        self.assertIn("resumptionToken=", fake.urls[1])
        self.assertNotIn("from=", fake.urls[1])

    def test_lazy(self):
        fake = FakeOAI()
        it = oai.list_records("https://x.test/oai", fetcher=fake, delay=0)
        next(it)
        self.assertEqual(len(fake.urls), 1)

    def test_repeated_token_stops(self):
        def same_page(url):
            return Response(url=url, status=200, text=read("page1_oai_openaire.xml"), fetched_at=None)
        with self.assertRaises(oai.OAIError) as cm:
            list(oai.iter_pages("https://x.test/oai", fetcher=same_page, delay=0))
        self.assertEqual(cm.exception.code, "loop")

    def test_no_records_match_single_request(self):
        fake = FakeOAI(first="no_records_match.xml")
        self.assertEqual(list(oai.list_records("https://x.test/oai", fetcher=fake, delay=0)), [])
        self.assertEqual(len(fake.urls), 1)


# --- mapping ---------------------------------------------------------------------------
class OpenAireRecordTest(unittest.TestCase):
    def setUp(self):
        p = page("page1_oai_openaire.xml")
        self.recs = [bn.build_record(r, metadata_prefix="oai_openaire", page_url=p.url, fetched_at=p.fetched_at,
                                     set_names=SETS, raw_page="run/page-0001.xml") for r in p.records]
        self.r = self.recs[0]

    def test_identity(self):
        r = self.r
        self.assertEqual(r["schema"], RECORD_SCHEMA)
        self.assertEqual(r["source"], "bibliotekanauki")
        self.assertEqual(r["record_id"], "5166")
        self.assertEqual(r["url"], "https://bibliotekanauki.pl/articles/5166")
        self.assertEqual(r["record_type"], "scientific_article")
        self.assertEqual(r["extra"]["category"], "nauka")

    def test_text(self):
        r = self.r
        self.assertEqual(r["title"], "Wykorzystanie odpadów z przetwórstwa mięsnego na cele energetyczne")
        self.assertEqual(r["language"], "pl")
        self.assertGreater(len(r["text"]["abstract"]), 200)
        self.assertIn("en", r["text"]["abstracts_other"])
        self.assertEqual(r["publication"]["titles"]["en"], "The usage of waste from meat processing for energetic purposes")
        self.assertTrue(r["text_for_llm"].startswith("Tytuł: Wykorzystanie odpadów"))
        self.assertIn("Słowa kluczowe: gospodarka odpadami", r["text_for_llm"])

    def test_keywords(self):
        self.assertEqual(self.r["keywords"][:3], ["gospodarka odpadami", "przetworstwo miesa", "odpady produkcyjne"])
        self.assertIn("biogaz", self.r["keywords"])

    def test_authors_and_affiliations(self):
        r = self.r
        self.assertEqual([p["name"] for p in r["people"]][:2], ["K. Kozlowski", "M. Cieslik"])
        self.assertEqual(r["people"][0]["family"], "Kozlowski")
        affs = [o for o in r["organizations"] if o["role"] == "author_affiliation"]
        self.assertEqual(len(affs), 1)  # five authors, one institution
        self.assertEqual(affs[0]["name"], "Uniwersytet Przyrodniczy w Poznaniu")
        self.assertEqual(affs[0]["location"]["city"], "Poznań")
        self.assertEqual(affs[0]["type_hint"], "university")
        self.assertEqual(len(affs[0]["authors"]), 5)
        pubs = [o for o in r["organizations"] if o["role"] == "publisher"]
        self.assertTrue(pubs[0]["name"].startswith("Uniwersytet Ekonomiczny we Wrocławiu"))

    def test_company_affiliation(self):
        affs = [o["name"] for o in self.recs[1]["organizations"] if o["role"] == "author_affiliation"]
        self.assertEqual(affs, ["PHU Plewex Pawel Plewa", "Uniwersytet Ekonomiczny we Wrocławiu", "Akademia Morska w Gdyni"])

    def test_publication_and_rights(self):
        pub, rights = self.r["publication"], self.r["rights"]
        self.assertEqual(pub["year"], 2015)
        self.assertEqual(pub["doi"], "10.15611/nit.2015.1.04")
        self.assertEqual(pub["journal"], "Nauki Inżynierskie i Technologie")  # from ListSets
        self.assertEqual(pub["pdf_url"], "https://bibliotekanauki.pl/articles/5166.pdf")
        self.assertEqual(rights["licence"], "all-rights-reserved")
        self.assertFalse(rights["llm_may_read_fulltext"])

    def test_quality_and_provenance(self):
        r = self.r
        self.assertEqual(r["quality"]["status"], "ok")
        self.assertNotIn("no_doi", r["quality"]["warnings"])
        prov = r["provenance"]
        self.assertEqual(prov["oai_identifier"], "oai:bibliotekanauki.pl:5166")
        self.assertEqual(prov["metadata_prefix"], "oai_openaire")
        self.assertEqual(prov["raw_page"], "run/page-0001.xml")
        self.assertTrue(prov["datestamp"])
        self.assertEqual(r["period"]["start"], None)  # a publication date is not a project period

    def test_hash_ignores_datestamp(self):
        p = page("page1_oai_openaire.xml")
        rec = p.records[0]
        rec.header.datestamp = "2030-01-01T00:00:00Z"
        again = bn.build_record(rec, metadata_prefix="oai_openaire", page_url=None, fetched_at=None, set_names=SETS)
        self.assertEqual(again["content_hash"], self.r["content_hash"])


class DublinCoreRecordTest(unittest.TestCase):
    def setUp(self):
        p = page("page_oai_dc.xml")
        live = [r for r in p.records if not r.header.deleted]
        self.assertEqual(len(live), 1)
        self.r = bn.build_record(live[0], metadata_prefix="oai_dc", page_url=p.url, fetched_at=p.fetched_at)

    def test_fields(self):
        r = self.r
        self.assertEqual(r["record_id"], "436948")
        self.assertTrue(r["title"].startswith("Rewolucja seksualna na Białorusi"))  # Polish title preferred
        self.assertEqual(r["publication"]["journal"], "Przegląd Środkowo-Wschodni")
        self.assertEqual(r["publication"]["issue"], "2017, 2")
        self.assertEqual(r["publication"]["pages"], "9-59")
        self.assertEqual(r["publication"]["issn"], ["2543-618X", "2545-1324"])
        self.assertEqual(r["publication"]["doi"], "10.32612/uw.2543618X.2017.pp.9-59")
        self.assertEqual(r["rights"]["licence"], "CC-BY-3.0-PL")
        self.assertTrue(r["rights"]["llm_may_read_fulltext"])
        self.assertEqual(r["people"][0]["family"], "Гужалоўскі")

    def test_gaps_of_oai_dc_are_warnings(self):
        w = self.r["quality"]["warnings"]
        self.assertIn("no_keywords_in_oai_dc", w)
        self.assertIn("no_affiliation_in_oai_dc", w)
        self.assertEqual(self.r["quality"]["status"], "ok")


class HelpersTest(unittest.TestCase):
    def test_licence(self):
        self.assertEqual(bn.licence_id(["CC BY: Creative Commons Uznanie autorstwa 4.0"]), ("CC-BY-4.0", True))
        self.assertEqual(bn.licence_id(["CC BY-NC-ND: Creative Commons Uznanie autorstwa - Użycie niekomercyjne"
                                        " - Bez utworów zależnych 3.0 PL"])[0], "CC-BY-NC-ND-3.0-PL")
        self.assertEqual(bn.licence_id([]), ("unknown", False))

    def test_split_affiliation(self):
        self.assertEqual(bn.split_affiliation("Politechnika Rzeszowska, Rzeszów"), ("Politechnika Rzeszowska", "Rzeszów"))
        # the tail is a sub-unit, not a city
        self.assertEqual(bn.split_affiliation("Politechnika Rzeszowska, Wydział Chemiczny")[1], None)
        self.assertEqual(bn.split_affiliation("Uniwersytet Rzeszowski"), ("Uniwersytet Rzeszowski", None))

    def test_iso_lang(self):
        self.assertEqual(bn.iso_lang("pol"), "pl")
        self.assertEqual(bn.iso_lang("eng"), "en")
        self.assertIsNone(bn.iso_lang(None))


# --- harvest + CLI ------------------------------------------------------------------------
class HarvestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = bn.RawStore(self.root / "raw")

    def tearDown(self):
        self.tmp.cleanup()

    def test_online_then_offline(self):
        fake, stats, sleeps = FakeOAI(), bn.HarvestStats(), []
        recs = list(bn.harvest(self.store, fetcher=fake, from_="2026-11-01", stats=stats, sleep=sleeps.append))
        self.assertEqual([r["record_id"] for r in recs], ["5166", "5175", "5164"])
        self.assertEqual(stats.pages, 2)
        self.assertEqual(stats.deleted, ["429121"])
        self.assertEqual(recs[0]["publication"]["journal"], "Nauki Inżynierskie i Technologie")
        self.assertIn("verb=ListSets", fake.urls[0])
        self.assertTrue(all("metadataPrefix=oai_openaire" in u for u in fake.urls[1:2]))
        self.assertEqual(recs[2]["provenance"]["raw_page"], "oai_openaire-all-2026-11-01-now/page-0002.xml")

        offline = list(bn.harvest(self.store, fetcher=None, offline=True))  # any window: falls back to latest
        self.assertEqual([r["content_hash"] for r in offline], [r["content_hash"] for r in recs])

    def test_limit_stops_paging(self):
        fake = FakeOAI()
        recs = list(bn.harvest(self.store, fetcher=fake, limit=2, with_sets=False, sleep=lambda s: None))
        self.assertEqual(len(recs), 2)
        self.assertEqual(len(fake.urls), 1)  # second page never requested

    def test_sets_failure_is_not_fatal(self):
        recs = list(bn.harvest(self.store, fetcher=FakeOAI(fail_sets=True), limit=1, sleep=lambda s: None))
        self.assertIsNone(recs[0]["publication"]["journal"])

    def test_sets_cached(self):
        fake = FakeOAI()
        list(bn.harvest(self.store, fetcher=fake, limit=1, sleep=lambda s: None))
        fake.urls.clear()
        list(bn.harvest(self.store, fetcher=fake, limit=1, sleep=lambda s: None))
        self.assertFalse(any("ListSets" in u for u in fake.urls))

    def test_offline_without_cache(self):
        with self.assertRaises(FileNotFoundError):
            list(bn.harvest(self.store, offline=True))

    def test_unknown_prefix(self):
        with self.assertRaises(ValueError):
            list(bn.harvest(self.store, fetcher=FakeOAI(), metadata_prefix="jats"))

    def test_main_offline_outputs(self):
        list(bn.harvest(self.store, fetcher=FakeOAI(), from_="2026-11-01", sleep=lambda s: None))
        out, csv_path, deleted = self.root / "o.jsonl", self.root / "o.csv", self.root / "deleted.txt"
        rc = bn.main(["--offline", "--raw-dir", str(self.store.root), "--from", "2026-11-01", "--out", str(out),
                      "--csv", str(csv_path), "--deleted-out", str(deleted), "--limit", "2"])
        self.assertEqual(rc, 0)
        lines = out.read_text("utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["source"], "bibliotekanauki")
        self.assertIn("Uniwersytet Przyrodniczy w Poznaniu", csv_path.read_text("utf-8-sig"))
        self.assertEqual(deleted.read_text("utf-8"), "")  # limit hit before the deleted header on page 2


if __name__ == "__main__":
    unittest.main()
