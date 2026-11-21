import gzip
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest import mock

from radar import store
from radar.crawl import __main__ as cli
from radar.crawl.crawler import crawl_due, crawl_site, discover_sitemaps, totals
from radar.crawl.fetcher import Fetcher
from tests.crawl_fixtures import ARTICLE, CHALLENGE, LIST, PRIVACY, SITEMAP, FakeWeb, html, make_site

BASE = "https://ctt.example.pl"
GONE_PAGE = ARTICLE.replace("Czujnik wilgotności gleby z AI", "Wpis, który zniknie").replace("czujnik", "zniknie")


def pages():
    return {
        f"{BASE}/aktualnosci": html(LIST, etag='"lista-1"'),
        f"{BASE}/aktualnosci/czujnik-gleby": html(ARTICLE, etag='"art-1"'),
        f"{BASE}/aktualnosci/polityka": html(PRIVACY),
        f"{BASE}/aktualnosci/zniknie": html(GONE_PAGE),
    }


def make_due(conn):
    conn.execute("UPDATE crawl_pages SET next_due='2000-01-01T00:00:00+00:00' WHERE next_due IS NOT NULL")
    conn.commit()


class CrawlerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raw = Path(self.tmp.name) / "raw"
        self.conn = store.connect(":memory:")
        self.site = make_site()
        self.web = FakeWeb(pages())
        self.fetcher = Fetcher(delay=0, opener=self.web, sleep=lambda s: None)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def crawl(self, **kw):
        return crawl_site(self.conn, self.site, self.fetcher, raw_root=self.raw, **kw)

    def page(self, path):
        return dict(self.conn.execute("SELECT * FROM crawl_pages WHERE url=?", (BASE + path,)).fetchone())

    def test_first_pass_builds_records(self):
        st = self.crawl()
        self.assertEqual(st["status"], "ok")
        # list + 3 linked pages + /aktualnosci/inny-wpis (linked from the article, 404)
        self.assertEqual((st["fetched"], st["lists"], st["added"], st["skipped"], st["gone"]), (5, 1, 2, 1, 1))
        self.assertEqual(self.page("/aktualnosci")["status"], "list")
        art = self.page("/aktualnosci/czujnik-gleby")
        self.assertEqual((art["status"], art["depth"]), ("record", 1))
        self.assertEqual(self.page("/aktualnosci/polityka")["status"], "skipped")

        rows = store.list_records(self.conn, category="nauka")
        self.assertEqual(len(rows), 2)
        rec = json.loads(next(r for r in rows if r["record_id"] == art["record_id"])["data"])
        self.assertEqual(rec["source"], "web_ctt_test")
        self.assertEqual(rec["title"], "Czujnik wilgotności gleby z AI")
        self.assertEqual(rec["extra"]["published"], "2026-03-14")
        self.assertEqual(rec["period"]["start"][:4], "2024")
        self.assertEqual(rec["funding"]["total_value"], 1200000.0)
        names = [o["name"] for o in rec["organizations"]]
        self.assertEqual(names[0], "Politechnika Rzeszowska")
        self.assertTrue(any("AgroSensor" in n for n in names), names)
        self.assertIn("podkarpackie", rec["region"]["voivodeships"])
        raw = Path(rec["provenance"]["raw_files"]["page"])
        self.assertTrue(raw.exists())
        self.assertIn(b"Czujnik", gzip.decompress(raw.read_bytes()))

        # out of scope links were never requested
        self.assertFalse(any("inna-domena" in u or "/kontakt" in u or ".pdf" in u for u in self.web.urls()))
        self.assertEqual(self.conn.execute("SELECT status FROM crawl_sites").fetchone()[0], "ok")

    def test_second_pass_uses_conditional_get_and_changes_nothing(self):
        self.crawl()
        make_due(self.conn)
        before = len(self.web.requests)
        st = self.crawl()
        self.assertEqual(st["added"], 0)
        self.assertEqual(st["not_modified"], 2)  # list + article answered 304 to If-None-Match
        self.assertEqual(st["unchanged"], 2)     # the others: same content hash
        sent = dict(self.web.requests[before:])
        self.assertEqual(sent[f"{BASE}/aktualnosci/czujnik-gleby"].get("if-none-match"), '"art-1"')

    def test_page_gone_twice_removes_record(self):
        self.crawl()
        rid = self.page("/aktualnosci/zniknie")["record_id"]
        del self.web.pages[f"{BASE}/aktualnosci/zniknie"]
        make_due(self.conn)
        self.crawl()
        self.assertEqual(self.page("/aktualnosci/zniknie")["status"], "gone")
        self.assertEqual(len(store.list_records(self.conn)), 2)  # one miss is not enough
        make_due(self.conn)
        st = self.crawl()
        self.assertEqual((self.page("/aktualnosci/zniknie")["status"], st["removed"]), ("gone_final", 1))
        live = [r["record_id"] for r in store.list_records(self.conn)]
        self.assertNotIn(rid, live)
        make_due(self.conn)
        self.crawl()
        self.assertEqual(self.web.urls().count(f"{BASE}/aktualnosci/zniknie"), 3)  # not visited again

    def test_blocked_start_page_stops_site(self):
        self.web.pages[f"{BASE}/aktualnosci"] = (403, CHALLENGE, {})
        st = self.crawl()
        self.assertEqual((st["status"], st["fetched"]), ("blocked", 1))
        self.assertEqual(self.conn.execute("SELECT status FROM crawl_sites").fetchone()[0], "blocked")
        self.assertEqual(self.page("/aktualnosci")["status"], "blocked")

    def test_page_budget_and_errors(self):
        st = self.crawl(max_pages=2)
        self.assertEqual(st["fetched"], 2)
        self.web.pages[f"{BASE}/aktualnosci/polityka"] = (500, "awaria", {})
        st = self.crawl(max_pages=10)
        self.assertEqual(st["errors"], 1)
        self.assertEqual(self.page("/aktualnosci/polityka")["status"], "error")

    def test_robots_disallow(self):
        self.web.pages[f"{BASE}/robots.txt"] = (200, "User-agent: *\nDisallow: /aktualnosci/polityka\n",
                                                {"Content-Type": "text/plain"})
        st = self.crawl()
        self.assertEqual(st["robots"], 1)
        self.assertEqual(self.page("/aktualnosci/polityka")["status"], "robots")
        self.assertNotIn(f"{BASE}/aktualnosci/polityka", self.web.urls())

    def test_dry_run_writes_no_raw_files(self):
        st = self.crawl(dry_run=True)
        self.assertEqual(st["added"], 2)
        self.assertFalse(self.raw.exists())
        kept = [d for d in st["decisions"] if d["keep"]]
        self.assertTrue(all(d["reason"] for d in st["decisions"]))
        self.assertIn("Politechnika Rzeszowska", kept[0]["organizations"])

    def test_require_date_drops_undated_pages(self):
        undated = ARTICLE.replace('"datePublished":"2026-03-14T09:00:00+01:00",', "")
        self.web.pages[f"{BASE}/aktualnosci/czujnik-gleby"] = html(undated)
        self.site = make_site(require_date=True)
        st = self.crawl()
        self.assertEqual(self.page("/aktualnosci/czujnik-gleby")["status"], "skipped")
        self.assertIn("brak daty", self.page("/aktualnosci/czujnik-gleby")["reason"])
        self.assertEqual(st["added"], 1)  # the dated page is still kept

    def test_sitemap_discovery(self):
        self.web.pages[f"{BASE}/sitemap.xml"] = (200, SITEMAP, {"Content-Type": "application/xml"})
        site = make_site(use_sitemap=True)
        added = discover_sitemaps(self.conn, site, self.fetcher)
        self.assertEqual(added, 2)  # wp-admin dropped by the scope rules
        urls = {r[0] for r in self.conn.execute("SELECT url FROM crawl_pages")}
        self.assertIn(f"{BASE}/aktualnosci/z-mapy", urls)

    def test_crawl_due_respects_interval(self):
        res = crawl_due(self.conn, [self.site], self.fetcher, raw_root=self.raw)
        self.assertEqual(len(res), 1)
        self.assertEqual(crawl_due(self.conn, [self.site], self.fetcher, raw_root=self.raw), [])  # nothing due yet
        self.assertEqual(len(crawl_due(self.conn, [self.site], self.fetcher, raw_root=self.raw, force=True)), 1)
        t = totals(res)
        self.assertEqual((t["sites"], t["added"], t["blocked_sites"]), (1, 2, []))


class CliTest(unittest.TestCase):
    def test_dry_run_and_sites_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "sites.json"
            site = make_site().to_json()
            cfg.write_text(json.dumps({"sites": [site]}), "utf-8")
            web = FakeWeb(pages())
            real = Fetcher
            with mock.patch.object(cli, "Fetcher", lambda: real(delay=0, opener=web, sleep=lambda s: None)):
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    rc = cli.main(["--config", str(cfg), "--dry-run", "--site", "ctt_test"])
            self.assertEqual(rc, 0)
            self.assertIn("REKORD  Czujnik wilgotności gleby z AI", out.getvalue())
            self.assertIn("pomiń", out.getvalue())

            db = Path(tmp) / "radar.db"
            with mock.patch.object(cli, "Fetcher", lambda: real(delay=0, opener=web, sleep=lambda s: None)):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    cli.main(["--config", str(cfg), "--db", str(db), "--raw-dir", str(Path(tmp) / "raw")])
            out = io.StringIO()
            with redirect_stdout(out):
                cli.main(["sites", "--config", str(cfg), "--db", str(db), "--json"])
            report = json.loads(out.getvalue())
            self.assertEqual(report[0]["records"], 2)
            self.assertEqual(report[0]["pages"]["record"], 2)

    def test_unknown_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "sites.json"
            cfg.write_text(json.dumps({"sites": [make_site().to_json()]}), "utf-8")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(["--config", str(cfg), "--site", "nie_ma", "--dry-run"]), 2)


if __name__ == "__main__":
    unittest.main()
