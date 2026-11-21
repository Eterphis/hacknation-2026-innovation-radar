import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from radar import refresh, store
from radar.http import BinaryResponse, Response
from tests.test_interreg import ROWS, make_xlsx

PAGE = '<a href="/wp-content/uploads/Wykaz_projektow_{tag}.xlsx">XLSX</a>'


class RefreshInterregTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "radar.db"
        self.page_tag = "20261116"
        self.content = make_xlsx(ROWS)
        self.downloads = 0
        patches = [
            mock.patch.object(refresh, "fetch", lambda url: Response(url, 200, PAGE.format(tag=self.page_tag), "2026-11-21T10:00:00+00:00")),
            mock.patch.object(refresh, "fetch_bytes", self._fetch_bytes),
            mock.patch.object(refresh, "LOCK_FILE", self.root / ".lock"),
            mock.patch.object(refresh, "STATE_FILE", self.root / "state.json"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def _fetch_bytes(self, url):
        self.downloads += 1
        return BinaryResponse(url, 200, self.content, "application/xlsx", "2026-11-21T10:00:01+00:00")

    def run_refresh(self, *extra):
        argv = ["--sources", "interreg", "--raw-dir", str(self.root / "raw"), "--out-dir", str(self.root / "norm"),
                "--db", str(self.db), *extra]
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            return refresh.main(argv)

    def runs(self):
        conn = store.connect(self.db)
        try:
            return store.refresh_runs(conn)
        finally:
            conn.close()

    def test_second_run_downloads_nothing_and_db_has_records(self):
        self.assertEqual(self.run_refresh(), 0)
        self.assertEqual(self.downloads, 1)
        first = self.runs()[0]
        self.assertEqual((first["download"], first["rebuild"], first["added"]), ("downloaded", "rebuilt", 2))

        self.assertEqual(self.run_refresh(), 0)
        self.assertEqual(self.downloads, 1)
        second = self.runs()[0]
        self.assertEqual((second["download"], second["rebuild"], second["added"]), ("skipped_already_have", "skipped_unchanged", 0))

        conn = store.connect(self.db)
        self.assertEqual(store.stats(conn)["records"], 2)
        conn.close()

    def test_meta_path_from_another_os_still_finds_the_file(self):
        self.run_refresh()
        meta_path = self.root / "raw" / "interreg" / "file.meta.json"
        meta = json.loads(meta_path.read_text("utf-8"))
        name = Path(meta["path"]).name
        meta["path"] = "C:\\elsewhere\\data\\raw\\interreg\\" + name  # written on Windows, read in a container
        meta_path.write_text(json.dumps(meta), "utf-8")
        self.assertEqual(self.run_refresh(), 0)
        self.assertEqual(self.downloads, 1)

    def test_new_file_on_page_is_downloaded(self):
        self.run_refresh()
        self.page_tag = "20261201"
        self.run_refresh()
        self.assertEqual(self.downloads, 2)

    def test_broken_download_keeps_previous_file(self):
        self.run_refresh()
        self.page_tag = "20261201"
        self.content = b"<html>blad serwera</html>"
        self.assertEqual(self.run_refresh(), 1)
        self.assertFalse(self.runs()[0]["ok"])
        saved = (self.root / "raw" / "interreg" / "file.meta.json").read_text("utf-8")
        self.assertIn("20261116", saved)

    def test_unreachable_page_rebuilds_from_saved_file_with_warning(self):
        self.run_refresh()
        (self.root / "norm" / "interreg.jsonl").unlink()  # e.g. a fresh checkout with the raw cache copied in

        def down(url):
            raise refresh.FetchError(f"giving up on {url}: timed out")

        with mock.patch.object(refresh, "fetch", down):
            self.assertEqual(self.run_refresh(), 1)  # warning -> exit code 1, but the source is not failed
        run = self.runs()[0]
        self.assertTrue(run["ok"])
        self.assertEqual((run["download"], run["rebuild"], run["records"]), ("unreachable_using_saved", "rebuilt", 2))
        self.assertIn("niedostępna", run["warning"])
        self.assertEqual(self.downloads, 1)

    def test_unreachable_page_without_saved_file_fails(self):
        def down(url):
            raise refresh.FetchError(f"giving up on {url}: timed out")

        with mock.patch.object(refresh, "fetch", down):
            self.assertEqual(self.run_refresh(), 1)
        self.assertFalse(self.runs()[0]["ok"])

    def test_dry_run_writes_nothing(self):
        self.assertEqual(self.run_refresh("--dry-run"), 0)
        self.assertEqual(self.downloads, 0)
        self.assertFalse((self.root / "raw").exists())
        self.assertEqual(self.runs(), [])

    def test_removed_rows_are_marked_in_db(self):
        self.run_refresh()
        self.page_tag = "20261201"
        self.content = make_xlsx(ROWS[:-1])
        self.run_refresh()
        self.assertEqual(self.runs()[0]["removed"], 1)

    def test_records_get_category(self):
        self.run_refresh()
        conn = store.connect(self.db)
        self.assertEqual(store.stats(conn)["categories"], {"projekty": 2})
        conn.execute("UPDATE records SET category=NULL")  # as loaded by the v1 refresh
        conn.commit()
        self.assertEqual(refresh.backfill_categories(conn), 2)
        conn.close()


class ScheduleTest(unittest.TestCase):
    def setUp(self):
        self.conn = store.connect(":memory:")
        self.src = refresh.SOURCES["interreg"]

    def add_run(self, hours_ago, ok=True):
        from datetime import datetime, timedelta, timezone
        at = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(timespec="seconds")
        store.add_refresh_run(self.conn, "interreg", {"ok": ok, "at": at, "rebuild": "rebuilt"})

    def test_due_by_interval_and_failed_retry(self):
        self.assertTrue(refresh.is_due(self.conn, self.src)[0])  # never run
        self.add_run(2)
        due, why = refresh.is_due(self.conn, self.src)
        self.assertFalse(due)
        self.assertIn("następny za", why)
        self.add_run(25)  # written later but older: the most recent run by time decides
        self.assertFalse(refresh.is_due(self.conn, self.src)[0])

        self.conn = store.connect(":memory:")
        self.add_run(7, ok=False)  # a failed run is retried after 6 h, not 24 h
        self.assertTrue(refresh.is_due(self.conn, self.src)[0])
        self.add_run(3, ok=False)
        self.assertFalse(refresh.is_due(self.conn, self.src)[0])

    def test_registry_is_consistent(self):
        ids = [s.id for s in refresh.REGISTRY]
        self.assertEqual(len(ids), len(set(ids)))
        for s in refresh.REGISTRY:
            self.assertIn(s.kind, ("api", "web", "import"))
            self.assertIn(s.category, ("nauka", "projekty", "biznes", "administracja", "mixed"))
        self.assertEqual(refresh.SOURCES["web"].writes_db, True)

    def test_incremental_source_does_not_remove_missing_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "okno.jsonl"
            rec = lambda rid: {"schema": "radar.record/v1", "source": "okno_src", "record_id": rid, "title": rid,
                               "content_hash": rid, "quality": {"status": "ok"}}
            out.write_text("\n".join(json.dumps(rec(r)) for r in ("a", "b", "c")), "utf-8")
            src = refresh.Source("okno", None, "nauka", "api", 168, lambda a, p: {}, incremental=True)
            res = {"rebuild": "rebuilt"}
            refresh.load_into_db(self.conn, src, out, res)
            out.write_text(json.dumps(rec("d")), "utf-8")  # next window: only a new record
            res = {"rebuild": "rebuilt"}
            refresh.load_into_db(self.conn, src, out, res)
            self.assertEqual((res["added"], res["removed"]), (1, 0))
            self.assertEqual(store.stats(self.conn)["categories"], {"nauka": 4})


class WebSourceTest(unittest.TestCase):
    def setUp(self):
        from radar.crawl.fetcher import Fetcher
        from tests.crawl_fixtures import ARTICLE, LIST, FakeWeb, html, make_site
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        cfg = self.root / "sites.json"
        cfg.write_text(json.dumps({"sites": [make_site().to_json(),
                                             make_site(id="gmina", category="administracja").to_json()]}), "utf-8")
        self.cfg = cfg
        web = FakeWeb({"https://ctt.example.pl/aktualnosci": html(LIST),
                       "https://ctt.example.pl/aktualnosci/czujnik-gleby": html(ARTICLE)})
        for p in (mock.patch("radar.crawl.crawler.Fetcher", lambda: Fetcher(delay=0, opener=web, sleep=lambda s: None)),
                  mock.patch.object(refresh, "LOCK_FILE", self.root / ".lock"),
                  mock.patch.object(refresh, "STATE_FILE", self.root / "state.json")):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def run_refresh(self, *extra):
        argv = ["--sources", "web", "--sites-config", str(self.cfg), "--raw-dir", str(self.root / "raw"),
                "--out-dir", str(self.root / "norm"), "--db", str(self.root / "radar.db"), *extra]
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = refresh.main(argv)
        return rc, err.getvalue()

    def test_web_source_crawls_and_due_only_waits(self):
        rc, _ = self.run_refresh("--category", "nauka")
        self.assertEqual(rc, 0)
        conn = store.connect(self.root / "radar.db")
        self.assertEqual(store.stats(conn)["categories"], {"nauka": 1})
        run = store.refresh_runs(conn)[0]
        self.assertEqual((run["source"], run["ok"], run["added"]), ("web", 1, 1))
        conn.close()
        rc, log = self.run_refresh("--due-only")
        self.assertIn("web: pomijam", log)  # ran less than an hour ago
        conn = store.connect(self.root / "radar.db")
        self.assertEqual(len(store.refresh_runs(conn)), 1)
        conn.close()


if __name__ == "__main__":
    unittest.main()


class LockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / ".lock"

    def tearDown(self):
        self.tmp.cleanup()

    def test_lock_from_another_host_blocks(self):
        self.path.write_text('{"pid": 1, "host": "inny-kontener", "started": "x"}', "utf-8")
        with self.assertRaises(SystemExit):
            with refresh.Lock(self.path):
                pass

    def test_lock_of_dead_local_process_is_taken_over(self):
        import socket
        self.path.write_text(json.dumps({"pid": 2 ** 22 + 7, "host": socket.gethostname()}), "utf-8")
        with contextlib.redirect_stderr(io.StringIO()):
            with refresh.Lock(self.path):
                self.assertTrue(self.path.exists())
        self.assertFalse(self.path.exists())

    def test_foreign_lock_is_not_removed_on_exit(self):
        with refresh.Lock(self.path):
            self.path.write_text('{"pid": 1, "host": "inny-kontener"}', "utf-8")  # someone took it over
        self.assertTrue(self.path.exists())
