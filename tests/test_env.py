import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from radar.env import load_env


class LoadEnvTest(unittest.TestCase):
    def test_parses_quotes_export_comments_and_keeps_existing(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text("# klucze\nOPENALEX_API_KEY='abc 123'\nexport OPENALEX_MAILTO=a@b.pl  # kontakt\n"
                         "RADAR_DB=\"x.db\"\nnot a line\nKEEP=from-file\n", "utf-8")
            with mock.patch.dict(os.environ, {"KEEP": "from-env"}, clear=True):
                names = load_env(p)
                self.assertEqual(os.environ["OPENALEX_API_KEY"], "abc 123")
                self.assertEqual(os.environ["OPENALEX_MAILTO"], "a@b.pl")
                self.assertEqual(os.environ["RADAR_DB"], "x.db")
                self.assertEqual(os.environ["KEEP"], "from-env")
                self.assertEqual(sorted(names), ["OPENALEX_API_KEY", "OPENALEX_MAILTO", "RADAR_DB"])

    def test_missing_file_is_fine(self):
        self.assertEqual(load_env(Path(tempfile.gettempdir()) / "no-such-dir" / ".env"), [])


if __name__ == "__main__":
    unittest.main()
