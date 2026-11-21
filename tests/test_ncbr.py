import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from radar import RECORD_SCHEMA
from radar.http import FetchError, Response
from radar.sources import ncbr

FIX = Path(__file__).parent / "fixtures" / "ncbr"
TODAY = date(2026, 11, 21)
CZUJNIK = "https://www.gov.pl/web/ncbr/innowacyjny-czujnik-odksztalcen-na-bazie-specjalnych-swiatlowodow-mikrostrukturalnych"


def read(name: str) -> str:
    return (FIX / name).read_text("utf-8")


class ParseListTest(unittest.TestCase):
    def setUp(self):
        self.cards = ncbr.parse_list(read("list_sample.html"))

    def test_all_cards_found(self):
        self.assertEqual(len(self.cards), 3)

    def test_card_fields(self):
        c = self.cards[0]
        self.assertEqual(c.detail_url, CZUJNIK)
        self.assertEqual(c.fields["contest"], ["LIDER VI"])
        self.assertEqual(c.fields["region"], ["województwo lubelskie"])
        self.assertEqual(c.fields["keywords"], ["Inżynieria materiałowa"])
        self.assertEqual(c.fields["total_value"], ["1 186 431,74 zł"])
        self.assertEqual(c.other, [])

    def test_link_text_not_a_value(self):
        for c in self.cards:
            for values in c.fields.values():
                self.assertFalse(any("Dowiedz" in v for v in values))


class ParseDetailTest(unittest.TestCase):
    def test_sections(self):
        d = ncbr.parse_detail(read("detail_czujnik.html"))
        self.assertTrue(d.title.startswith("Innowacyjny czujnik"))
        self.assertTrue(d.intro.startswith("Wzrost tempa automatyzacji"))
        for key in ("problem", "users", "challenges", "advice", "result", "team"):
            self.assertIn(key, d.fields, key)
        self.assertIn("da Vinci", d.fields["users"][0])
        self.assertEqual(d.fields["team"], ["Kierownik projektu - dr inż. Marek Napierała"])

    def test_other_pages_have_core_sections(self):
        for name in ("detail_5.html", "detail_13.html"):
            d = ncbr.parse_detail(read(name))
            self.assertIn("problem", d.fields, name)
            self.assertIn("users", d.fields, name)

    def test_no_article(self):
        self.assertIsNone(ncbr.parse_detail("<html><body>Site is under high load</body></html>"))


class InlineLabelsTest(unittest.TestCase):
    def test_crammed_card(self):
        text = ("Wartość projektu 1 325 221,00 zł Wartość dofinansowania 1 148 750,00 zł "
                "Okres realizacji projektu 1 lipca 2015 r. – 31 maja 2019 r. Region:")
        self.assertEqual(ncbr.split_inline(text), [
            ("total_value", "1 325 221,00 zł"),
            ("grant_value", "1 148 750,00 zł"),
            ("period", "1 lipca 2015 r. – 31 maja 2019 r"),
            ("region", ""),
        ])

    def test_plain_text_is_not_split(self):
        self.assertIsNone(ncbr.split_inline("Projekt dotyczy konkursu dla szkół"))

    def test_label_key(self):
        self.assertEqual(ncbr.label_key("​ Tytuł projektu"), "title")
        self.assertEqual(ncbr.label_key("Słowa kluczowe:"), "keywords")
        self.assertEqual(ncbr.label_key("Kto skorzysta z wyników projektu?"), "users")
        self.assertEqual(ncbr.label_key("Kto korzysta/skorzysta z wyników projektu?"), "users")
        self.assertIsNone(ncbr.label_key("Konkursy w szkołach podstawowych to dobra metoda"))

    def test_commercialisation_template(self):
        self.assertEqual(ncbr.label_key("Poznaj nasz zespół"), "team")
        self.assertEqual(ncbr.label_key("Zobaczcie efekt naszej pracy"), "result")
        self.assertEqual(ncbr.label_key(
            "Czy udało się Państwu stworzyć produkt czy technologię gotową do wykorzystania na rynku?"),
            "market_readiness")
        self.assertEqual(ncbr.label_key("Jak wyglądała ścieżka komercjalizacji wyników?"), "commercialization")
        self.assertEqual(ncbr.label_key("Jak uregulowano kwestię własności intelektualnej w projekcie."), "ip")
        html = ("<article><h2>T</h2><div><h3>Czy udało się Państwu stworzyć produkt gotowy?</h3>"
                "<p>" + "Tak, powstał produkt sprzedawany w sieci. " * 10 + "</p>"
                "<h3>Wideo</h3><p>Film o projekcie</p></div></article>")
        d = ncbr.parse_detail(html)
        self.assertIn("market_readiness", d.fields)
        self.assertEqual(d.other, [])  # video caption dropped, not dumped into other
        card = ncbr.Parsed(fields={"title": ["T"]}, detail_url="https://www.gov.pl/web/ncbr/t")
        r = ncbr.build_record(card, d, list_fetched_at=None, detail_fetched_at=None, today=TODAY)
        self.assertNotIn("missing_problem", r["quality"]["blocking"])


class PartiesTest(unittest.TestCase):
    def test_person_and_org(self):
        orgs, people = ncbr.parse_parties("Marek Adam Napierała, Polskie Centrum Fotoniki i Światłowodów", "beneficiary")
        self.assertEqual([o["name"] for o in orgs], ["Polskie Centrum Fotoniki i Światłowodów"])
        self.assertEqual([p["name"] for p in people], ["Marek Adam Napierała"])

    def test_subunit_stays_with_org(self):
        orgs, people = ncbr.parse_parties("Politechnika Rzeszowska, Wydział Budowy Maszyn i Lotnictwa", "beneficiary")
        self.assertEqual(len(orgs), 1)
        self.assertEqual(orgs[0]["type_hint"], "university")
        self.assertEqual(people, [])

    def test_several_orgs(self):
        orgs, _ = ncbr.parse_parties("Gmina Kęty; Instytut Lotnictwa", "partner")
        self.assertEqual([o["type_hint"] for o in orgs], ["local_government", "research_institute"])

    def test_team_with_titles(self):
        people = ncbr.parse_team(["Kierownik projektu - dr hab. inż. Anna Kowalska-Nowak, prof. PRz"])
        self.assertEqual(len(people), 1)
        self.assertEqual(people[0]["name"], "Anna Kowalska-Nowak")
        self.assertEqual(people[0]["role"], "Kierownik projektu")


class BuildRecordTest(unittest.TestCase):
    def setUp(self):
        self.card = ncbr.parse_list(read("list_sample.html"))[0]
        self.detail = ncbr.parse_detail(read("detail_czujnik.html"))

    def test_normalized_record(self):
        r = ncbr.build_record(self.card, self.detail, list_fetched_at="L", detail_fetched_at="D", today=TODAY)
        self.assertEqual(r["schema"], RECORD_SCHEMA)
        self.assertEqual(r["record_id"], CZUJNIK.rsplit("/", 1)[-1])
        self.assertEqual(r["funding"]["total_value"], 1186431.74)
        self.assertEqual(r["funding"]["grant_share"], 1.0)
        self.assertEqual(r["period"]["start"], "2016-02-01")
        self.assertEqual(r["period"]["status"], "finished")
        self.assertEqual(r["region"]["voivodeships"], ["lubelskie"])
        self.assertEqual(r["quality"], {"status": "ok", "blocking": [], "warnings": [],
                                        "narrative_chars": r["quality"]["narrative_chars"]})
        self.assertIn("Jaki problem rozwiązuje projekt:", r["text_for_llm"])
        self.assertNotIn("Zajawka:", r["text_for_llm"])  # intro repeats the problem section
        self.assertEqual({p["role"] for p in r["people"]}, {"beneficiary", "Kierownik projektu"})
        json.dumps(r)  # serializable

    def test_hash_is_stable(self):
        a = ncbr.build_record(self.card, self.detail, list_fetched_at="1", detail_fetched_at="1", today=TODAY)
        b = ncbr.build_record(self.card, self.detail, list_fetched_at="2", detail_fetched_at="2", today=TODAY)
        self.assertEqual(a["content_hash"], b["content_hash"])

    def test_missing_detail_needs_review(self):
        r = ncbr.build_record(self.card, None, list_fetched_at="L", detail_fetched_at=None,
                              detail_error="HTTP 404", today=TODAY)
        self.assertEqual(r["quality"]["status"], "needs_review")
        self.assertTrue(r["quality"]["blocking"][0].startswith("detail_fetch_failed"))
        self.assertEqual(r["funding"]["contest"], "LIDER VI")  # card data still kept


class HarvestTest(unittest.TestCase):
    def test_online_then_offline(self):
        pages = {ncbr.LIST_URL: read("list_sample.html"), CZUJNIK: read("detail_czujnik.html")}
        calls = []

        def fake_fetch(url):
            calls.append(url)
            if url not in pages:
                raise FetchError(f"HTTP 404 for {url}")
            return Response(url=url, status=200, text=pages[url], fetched_at="2026-11-21T12:00:00+00:00")

        with tempfile.TemporaryDirectory() as tmp:
            store = ncbr.RawStore(Path(tmp))
            stats = ncbr.HarvestStats()
            records = list(ncbr.harvest(store, fetcher=fake_fetch, delay=0, today=TODAY, stats=stats))
            self.assertEqual(len(records), 3)
            self.assertEqual(stats.cards, 3)
            self.assertEqual(stats.fetch_errors, 2)
            self.assertEqual([r["quality"]["status"] for r in records], ["ok", "needs_review", "needs_review"])

            # second run is fully offline from the raw store; failed pages stay failed, nothing is lost
            offline = list(ncbr.harvest(store, offline=True, today=TODAY))
            self.assertEqual(len(offline), 3)
            self.assertEqual(offline[0]["content_hash"], records[0]["content_hash"])
            self.assertEqual(offline[1]["quality"]["blocking"], ["detail_not_fetched"])
            self.assertEqual(len(calls), 4)  # list page + 3 detail pages, only in the online run
