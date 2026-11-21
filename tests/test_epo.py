import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from radar.http import FetchError, Response
from radar.sources import epo

FIXTURES = Path(__file__).parent / "fixtures" / "epo"
DOC = (FIXTURES / "EP3586762A1.xml").read_text("utf-8")

PUB = "http://data.epo.org/linked-data/data/publication/EP/3586762/A1/-"
APP = "http://data.epo.org/linked-data/id/application/EP/18180345"
XML_URL = "https://data.epo.org/linked-data/representation/publication/EP/3586762/NWA1.xml"


def sparql_answer(query: str) -> list[dict]:
    lit = lambda v: {"type": "literal", "value": v}  # noqa: E731
    uri = lambda v: {"type": "uri", "value": v}  # noqa: E731
    if "SELECT DISTINCT ?pub ?app" in query:
        return [{"pub": uri(PUB), "app": uri(APP), "kind": uri(epo.PAT + "publicationKind_A1"),
                 "num": lit("3586762"), "d": lit("2020-01-01")}]
    if "titleOfInvention" in query:
        return [{"pub": uri(PUB), "t": lit("CANNULA FOR VALVE REPAIR"), "l": lit("en")},
                {"pub": uri(PUB), "t": lit("KANÜLE"), "l": lit("de")}]
    if "applicantVC ?vc BIND" in query:
        return [{"pub": uri(PUB), "role": lit("applicant"), "name": lit("Medinice S.A."), "cc": lit("PL")},
                {"pub": uri(PUB), "role": lit("inventor"), "name": lit("SUWALSKI, Piotr"), "cc": lit("PL")}]
    if "pat:representation" in query:
        return [{"pub": uri(PUB), "rep": uri(XML_URL)}]
    if "applicationNumberOriginal" in query:
        return [{"app": uri(APP), "num": lit("18180345"), "filed": lit("2018-06-28")}]
    if "classificationCPCInventive" in query:
        return [{"app": uri(APP), "c": uri("http://data.epo.org/linked-data/def/cpc/A61B17-12036")}]
    if "publicationKind_B1" in query:
        return [{"app": uri(APP), "g": uri("x"), "gnum": lit("3586762"), "gd": lit("2022-05-04")}]
    return []


class FakeFetcher:
    def __init__(self, doc_ok=True):
        self.calls, self.doc_ok = [], doc_ok

    def __call__(self, url, timeout=30, accept=""):
        self.calls.append(url)
        if url.startswith(epo.SPARQL_URL):
            q = parse_qs(urlparse(url).query)["query"][0]
            return Response(url, 200, json.dumps({"results": {"bindings": sparql_answer(q)}}), "2026-11-21T12:00:00+00:00")
        if not self.doc_ok:
            raise FetchError("HTTP 404")
        return Response(url, 200, DOC, "2026-11-21T12:00:01+00:00")


class EpoUnitTest(unittest.TestCase):
    def test_parse_document(self):
        d = epo.parse_document(DOC)
        self.assertEqual(d["abstract"], "A cannula for minimally invasive surgery & repair.")
        self.assertEqual(d["first_claim"], "A cannula comprising two tubes.")
        self.assertEqual(d["description"], "The object of the invention is a cannula.")  # comment removed
        self.assertEqual(d["applicants"][0], {"name": "Medinice S.A.", "street": "ul. Karola Olszewskiego 6",
                                              "postal_code": "25-663", "city": "Kielce", "country": "PL"})

    def test_codes_and_names(self):
        self.assertEqual(epo.code("http://data.epo.org/linked-data/def/cpc/B67C7-0026"), "B67C 7/0026")
        self.assertEqual(epo._name("NOWACKI, Tomasz"), "Tomasz Nowacki")
        self.assertEqual(epo._name("Suwalski, Piotr"), "Piotr Suwalski")
        self.assertEqual(epo._name("KOWALSKA-NOWAK, Anna"), "Anna Kowalska-Nowak")
        self.assertEqual(epo._pub_id(PUB), "EP3586762A1")

    def test_list_query_filters(self):
        q = epo.list_query("PL", "2020-01-01", "2021-01-01", 100, 200)
        for part in ('pat:countryCode "PL"', "publicationKind_A1", "publicationKind_A2", '"2020-01-01"^^xsd:date',
                     '"2021-01-01"^^xsd:date', "LIMIT 100 OFFSET 200"):
            self.assertIn(part, q)


class EpoHarvestTest(unittest.TestCase):
    def test_record_from_fake_endpoint_then_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = epo.RawStore(Path(tmp))
            fetcher = FakeFetcher()
            recs = list(epo.Harvester(store, fetcher=fetcher, delay=0).run())
            self.assertEqual(len(recs), 1)
            r = recs[0]
            self.assertEqual(r["record_id"], "ep-18180345")
            self.assertEqual(r["url"], "https://register.epo.org/application?number=EP18180345")
            self.assertEqual(r["title"], "CANNULA FOR VALVE REPAIR")
            self.assertEqual(r["patent"]["filing_date"], "2018-06-28")
            self.assertEqual(r["patent"]["grant"], {"publication": "EP3586762B1", "date": "2022-05-04"})
            self.assertEqual(r["patent"]["cpc"], ["A61B 17/12036"])
            self.assertEqual(r["organizations"][0]["location"]["city"], "Kielce")
            self.assertEqual(r["people"][0]["name"], "Piotr Suwalski")
            self.assertEqual(r["text"]["first_claim"], "A cannula comprising two tubes.")
            self.assertEqual(r["quality"]["status"], "ok")
            self.assertTrue(Path(r["provenance"]["raw_files"]["source_document"]).exists())

            offline = list(epo.Harvester(store, fetcher=None, offline=True, delay=0).run())
            self.assertEqual(offline[0]["content_hash"], r["content_hash"])

    def test_missing_document_is_a_warning_not_a_loss(self):
        with tempfile.TemporaryDirectory() as tmp:
            recs = list(epo.Harvester(epo.RawStore(Path(tmp)), fetcher=FakeFetcher(doc_ok=False), delay=0).run())
            self.assertEqual(len(recs), 1)
            self.assertEqual(recs[0]["quality"]["status"], "ok")
            self.assertTrue(recs[0]["quality"]["warnings"][0].startswith("document_not_fetched: HTTP 404"))
            self.assertIsNone(recs[0]["text"]["abstract"])


if __name__ == "__main__":
    unittest.main()
