import unittest

from radar.crawl.classify import classify
from radar.crawl.extract import best_title, extract_html, published_date
from tests.crawl_fixtures import ARTICLE, PRIVACY


class ClassifyTest(unittest.TestCase):
    def test_innovation_article_is_kept(self):
        page = extract_html(ARTICLE, "https://ctt.example.pl/aktualnosci/czujnik-gleby")
        sig = classify(best_title(page), page.body_text, published=published_date(page))
        self.assertTrue(sig.keep, sig.reason)
        self.assertGreaterEqual(sig.score, 2)
        self.assertIn("innovation", sig.hits)
        self.assertIn("project", sig.hits)
        self.assertEqual(sig.page_type, "project")
        self.assertIn("wynik", sig.reason)

    def test_service_page_is_skipped(self):
        page = extract_html(PRIVACY, "https://ctt.example.pl/aktualnosci/polityka")
        sig = classify(best_title(page), page.body_text)
        self.assertFalse(sig.keep)
        self.assertIn("strona serwisowa", sig.reason)

    def test_short_text_and_noindex(self):
        self.assertIn("za mało tekstu", classify("Innowacyjny prototyp", "Krótko o patencie.").reason)
        long = "Opracowano innowacyjny prototyp i zgłoszono patent. " * 20
        self.assertEqual(classify("Prototyp", long, noindex=True).reason, "noindex")

    def test_keep_all_and_threshold(self):
        plain = "Gmina ogłasza harmonogram odbioru odpadów w kolejnych miesiącach roku. " * 10
        self.assertFalse(classify("Harmonogram", plain).keep)
        self.assertTrue(classify("Harmonogram", plain, keep_all=True).keep)
        offer = "Oferta technologiczna: technologia do komercjalizacji, licencja na wynalazek. " * 8
        sig = classify("Oferta technologiczna", offer)
        self.assertEqual(sig.page_type, "technology_offer")
        self.assertTrue(sig.keep)

    def test_folding_matches_without_polish_letters(self):
        a = classify("Wdrożenie", "Wdrożenie innowacyjnej technologii wodorowej w przedsiębiorstwie. " * 10)
        b = classify("Wdrozenie", "Wdrozenie innowacyjnej technologii wodorowej w przedsiebiorstwie. " * 10)
        self.assertEqual(a.hits, b.hits)


if __name__ == "__main__":
    unittest.main()
