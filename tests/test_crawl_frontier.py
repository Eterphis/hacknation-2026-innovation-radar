import unittest

from radar import store
from radar.crawl.fetcher import Fetcher
from radar.crawl.frontier import canonical_url, due_pages, enqueue, in_scope, parse_sitemap, update_page
from tests.crawl_fixtures import SITEMAP, SITEMAP_INDEX, FakeWeb, html, make_site


class CanonicalTest(unittest.TestCase):
    def test_normalisation(self):
        self.assertEqual(canonical_url("HTTPS://Example.PL:443//a//b/?utm_source=x&b=2&a=1#frag"),
                         "https://example.pl/a/b/?a=1&b=2")
        self.assertEqual(canonical_url("../c?fbclid=1", "https://example.pl/a/b/"), "https://example.pl/a/c")
        self.assertEqual(canonical_url("http://example.pl:8080"), "http://example.pl:8080/")
        for bad in ("mailto:a@b.pl", "javascript:void(0)", "tel:123", "/relative-without-base"):
            self.assertIsNone(canonical_url(bad))


class ScopeTest(unittest.TestCase):
    def setUp(self):
        self.site = make_site(exclude=[r"/archiwum/"], follow=[r"^/aktualnosci/?$", r"[?&]strona=\d+"])

    def test_host_and_paths(self):
        self.assertTrue(in_scope(self.site, "https://ctt.example.pl/aktualnosci/czujnik"))
        self.assertTrue(in_scope(self.site, "https://www.ctt.example.pl/aktualnosci/czujnik"))  # www. ignored
        self.assertFalse(in_scope(self.site, "https://inna-domena.pl/aktualnosci/x"))
        self.assertFalse(in_scope(self.site, "https://ctt.example.pl/oferta"))           # outside include
        self.assertFalse(in_scope(self.site, "https://ctt.example.pl/aktualnosci/archiwum/x"))  # exclude
        self.assertFalse(in_scope(self.site, "https://ctt.example.pl/aktualnosci/plik.docx"))   # file types
        self.assertFalse(in_scope(self.site, "https://ctt.example.pl/aktualnosci/?s=szukaj"))   # search

    def test_follow_pages(self):
        self.assertTrue(self.site.is_follow("/aktualnosci"))
        self.assertTrue(self.site.is_follow("/lista?strona=2"))
        self.assertTrue(in_scope(self.site, "https://ctt.example.pl/lista?strona=2"))  # follow widens scope
        self.assertFalse(self.site.is_follow("/aktualnosci/czujnik"))


class SitemapTest(unittest.TestCase):
    def test_urlset_and_index(self):
        urls, nested = parse_sitemap(SITEMAP, "https://ctt.example.pl/sitemap.xml")
        self.assertEqual(urls[0], ("https://ctt.example.pl/aktualnosci/czujnik-gleby", "2026-03-20"))
        self.assertEqual(len(urls), 3)
        self.assertEqual(nested, [])
        urls, nested = parse_sitemap(SITEMAP_INDEX, "https://ctt.example.pl/sitemap.xml")
        self.assertEqual((urls, nested), ([], ["https://ctt.example.pl/sitemap-posts.xml"]))
        self.assertEqual(parse_sitemap("<to nie jest xml", "https://x.pl/"), ([], []))


class RobotsTest(unittest.TestCase):
    def test_robots_rules_and_sitemaps(self):
        web = FakeWeb({"https://ctt.example.pl/robots.txt": (200, "User-agent: *\nDisallow: /prywatne/\nCrawl-delay: 5\n"
                                                                  "Sitemap: https://ctt.example.pl/sm.xml\n",
                                                             {"Content-Type": "text/plain"}),
                       "https://ctt.example.pl/prywatne/a": html("<p>x</p>")})
        slept = []
        f = Fetcher(delay=0, opener=web, sleep=slept.append)
        self.assertFalse(f.allowed("https://ctt.example.pl/prywatne/a"))
        self.assertEqual(f.get("https://ctt.example.pl/prywatne/a").status, "robots")
        self.assertNotIn("https://ctt.example.pl/prywatne/a", web.urls())  # never requested
        self.assertEqual(f.crawl_delay("https://ctt.example.pl/"), 5.0)
        self.assertEqual(f.sitemaps("https://ctt.example.pl/"), ["https://ctt.example.pl/sm.xml"])

    def test_missing_robots_allows_and_forbidden_robots_closes(self):
        f = Fetcher(delay=0, opener=FakeWeb({}), sleep=lambda s: None)
        self.assertTrue(f.allowed("https://ctt.example.pl/a"))
        closed = FakeWeb({"https://zamk.pl/robots.txt": (403, "", {})})
        self.assertFalse(Fetcher(delay=0, opener=closed, sleep=lambda s: None).allowed("https://zamk.pl/a"))


class QueueTest(unittest.TestCase):
    def setUp(self):
        self.conn = store.connect(":memory:")
        self.site = make_site()

    def test_enqueue_is_idempotent_and_start_keeps_depth_zero(self):
        url = "https://ctt.example.pl/aktualnosci"
        self.assertTrue(enqueue(self.conn, self.site, url, 2))
        self.assertFalse(enqueue(self.conn, self.site, url, 0))
        self.assertEqual(self.conn.execute("SELECT depth FROM crawl_pages").fetchone()[0], 0)

    def test_due_pages_order_and_schedule(self):
        enqueue(self.conn, self.site, "https://ctt.example.pl/aktualnosci/b", 2)
        enqueue(self.conn, self.site, "https://ctt.example.pl/aktualnosci", 0)
        enqueue(self.conn, self.site, "https://ctt.example.pl/aktualnosci/c", 1)
        self.assertEqual([r["depth"] for r in due_pages(self.conn, self.site, 10)], [0, 1, 2])
        update_page(self.conn, "https://ctt.example.pl/aktualnosci/c", status="record", next_due="2999-01-01T00:00:00+00:00")
        update_page(self.conn, "https://ctt.example.pl/aktualnosci/b", status="gone_final", next_due=None)
        self.assertEqual([r["url"] for r in due_pages(self.conn, self.site, 10)], ["https://ctt.example.pl/aktualnosci"])


if __name__ == "__main__":
    unittest.main()
