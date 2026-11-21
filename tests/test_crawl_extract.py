import unittest

from radar.crawl.extract import best_title, description, extract_html, modified_date, published_date
from tests.crawl_fixtures import ARTICLE, EMPTY

URL = "https://ctt.example.pl/aktualnosci/czujnik-gleby"


class ExtractTest(unittest.TestCase):
    def setUp(self):
        self.page = extract_html(ARTICLE, URL)

    def test_main_text_without_boilerplate(self):
        text = self.page.text
        self.assertIn("prototyp czujnika wilgotności gleby", text)
        self.assertIn("Okres realizacji", text)
        for junk in ("plików cookies", "Deklaracja dostępności", "Kontakt", "al. Powstańców"):
            self.assertNotIn(junk, text)

    def test_heading_is_not_body(self):
        self.assertTrue(self.page.blocks[0].is_heading)
        self.assertNotIn("Czujnik wilgotności gleby z AI\n", self.page.body_text[:40])

    def test_metadata(self):
        self.assertEqual(self.page.lang, "pl")
        self.assertEqual(published_date(self.page), "2026-03-14")
        self.assertEqual(modified_date(self.page), "2026-03-20")
        self.assertEqual(best_title(self.page, "Centrum Transferu Technologii PRz"), "Czujnik wilgotności gleby z AI")
        self.assertTrue(description(self.page).startswith("Naukowcy opracowali"))
        self.assertEqual(self.page.canonical, URL)
        self.assertFalse(self.page.noindex)

    def test_links_include_nav_and_content(self):
        hrefs = [h for h, _ in self.page.links]
        self.assertIn("/aktualnosci/inny-wpis?utm_source=x", hrefs)
        self.assertIn("/kontakt", hrefs)  # links are collected everywhere; scope decides later

    def test_empty_page(self):
        page = extract_html(EMPTY, "https://ctt.example.pl/pusta")
        self.assertEqual(page.body_text, "")
        self.assertEqual(published_date(page), None)
        self.assertEqual(best_title(page), "Pusta")

    def test_noindex_and_broken_markup(self):
        page = extract_html('<html><head><meta name="robots" content="NOINDEX, follow"></head><body><main><p>Tekst '
                            '<b>bez zamknięcia<div>dalej', "https://x.pl/")
        self.assertTrue(page.noindex)
        self.assertIn("dalej", page.text)

    def test_boilerplate_class_on_body_does_not_hide_page(self):
        page = extract_html('<html><body class="wp-theme has-header menu-closed"><div class="mobile-nav"><a href="/">Start</a>'
                            '</div><main><section><p>' + "Zespół opracował prototyp. " * 20 + "</p></section></main></body></html>",
                            "https://x.pl/a")
        self.assertIn("opracował prototyp", page.body_text)
        self.assertNotIn("Start", page.body_text)

    def test_title_when_h1_is_the_site_logo(self):
        page = extract_html("<html><head><title>Fundusze Europejskie dla Podkarpacia 2021-2027 - Przebudowa DW 878 "
                            "Tyczyn – Dylągówka</title></head><body><h1>Fundusze Europejskie dla Podkarpacia 2021–2027</h1></body></html>",
                            "https://x.pl/p")
        self.assertEqual(best_title(page), "Przebudowa DW 878 Tyczyn – Dylągówka")
        page = extract_html("<html><head><title>Nowy laser w laboratorium | Portal Uczelni</title></head><body>"
                            "<h1>Portal Uczelni</h1></body></html>", "https://x.pl/q")
        self.assertEqual(best_title(page), "Nowy laser w laboratorium")

    def test_date_from_visible_text(self):
        page = extract_html("<html><body><main><p>Opublikowano 05.02.2026</p><p>" + "Treść. " * 60 + "</p></main></body></html>",
                            "https://x.pl/a")
        self.assertEqual(published_date(page), "2026-02-05")


if __name__ == "__main__":
    unittest.main()
