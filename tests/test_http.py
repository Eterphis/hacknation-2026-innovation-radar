import ssl
import unittest

from radar.http import ascii_url, ssl_context


class AsciiUrlTest(unittest.TestCase):
    def test_polish_path_is_percent_encoded(self):
        self.assertEqual(ascii_url("https://www.dolinalotnicza.pl/członkowie"),
                         "https://www.dolinalotnicza.pl/cz%C5%82onkowie")

    def test_query_and_existing_escapes(self):
        self.assertEqual(ascii_url("https://x.pl/a%20b?q=łódź&p=1"), "https://x.pl/a%20b?q=%C5%82%C3%B3d%C5%BA&p=1")

    def test_international_host(self):
        self.assertEqual(ascii_url("https://żółw.pl/x"), "https://xn--w-uga1v8h.pl/x")

    def test_ascii_url_unchanged(self):
        url = "https://bibliotekanauki.pl/api/oai/articles?verb=ListRecords&from=2026-11-11"
        self.assertIs(ascii_url(url), url)


class FetcherNonAsciiUrlTest(unittest.TestCase):
    def test_crawler_requests_a_polish_url(self):
        from radar.crawl.fetcher import Fetcher
        from tests.crawl_fixtures import FakeWeb, html

        web = FakeWeb({"https://ctt.example.pl/cz%C5%82onkowie": html("<h1>Członkowie</h1>")})
        res = Fetcher(delay=0, opener=web, sleep=lambda s: None).get("https://ctt.example.pl/członkowie")
        self.assertEqual(res.status, "ok")  # before: UnicodeEncodeError stopped the whole site
        self.assertIn("https://ctt.example.pl/cz%C5%82onkowie", web.urls())


class SslContextTest(unittest.TestCase):
    def test_verification_stays_on(self):
        ctx = ssl_context()
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(ctx.check_hostname)
        self.assertTrue(ctx.get_ca_certs())


if __name__ == "__main__":
    unittest.main()
