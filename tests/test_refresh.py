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
