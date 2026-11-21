import io
import json
import tempfile
import unittest
import urllib.error
import zipfile
from datetime import date
from email.message import Message
from pathlib import Path

from radar.sources import cordis
from radar.sources.dumps import download_if_changed

FIXTURES = Path(__file__).parent / "fixtures" / "cordis"
TODAY = date(2026, 11, 21)


def fixture_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in ("project.csv", "organization.csv"):
            z.writestr(name, (FIXTURES / name).read_bytes())
    return buf.getvalue()


class FakeResp(io.BytesIO):
    def __init__(self, data: bytes, url: str, headers: dict):
        super().__init__(data)
        self.status, self._url = 200, url
        self.headers = Message()
        for k, v in headers.items():
            self.headers[k] = v

    def geturl(self):
        return self._url


class FakeOpener:
    """Serves the fixture ZIP; answers 304 when the request carries the matching ETag."""

    def __init__(self, data: bytes, etag: str = '"abc"'):
        self.data, self.etag, self.requests = data, etag, []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        if req.get_header("If-none-match") == self.etag:
            raise urllib.error.HTTPError(req.full_url, 304, "Not Modified", Message(), None)
        return FakeResp(self.data, req.full_url, {"ETag": self.etag, "Last-Modified": "Tue, 10 Nov 2026 13:11:43 GMT"})


class CordisTest(unittest.TestCase):
    def test_read_dump_keeps_projects_with_polish_participant(self):
        projects, orgs = cordis.read_dump(fixture_zip())
        self.assertEqual(sorted(p["id"] for p in projects), ["101039066", "101039221"])
        self.assertNotIn("101039090", orgs)  # German-only project dropped
        self.assertEqual(len(orgs["101039221"]), 3)

    def test_build_record(self):
        projects, orgs = cordis.read_dump(fixture_zip())
        p = next(p for p in projects if p["id"] == "101039221")
        rec = cordis.build_record(p, orgs[p["id"]], programme="HORIZON", country="PL",
                                  file_meta={"url": cordis.DUMPS["HORIZON"], "fetched_at": "2026-11-21T12:00:00+00:00",
                                             "path": "x.zip"}, today=TODAY)
        self.assertEqual(rec["schema"], "radar.record/v1")
        self.assertEqual(rec["record_id"], "horizon-101039221")
        self.assertEqual(rec["url"], "https://cordis.europa.eu/project/id/101039221")
        self.assertEqual(rec["organizations"][0]["role"], "coordinator")  # coordinator first
        pl = [o for o in rec["organizations"] if o["is_target_country"]]
        self.assertEqual(len(pl), 1)
        self.assertIn("AKADEMIA GORNICZO-HUTNICZA", pl[0]["name"])
        self.assertEqual(pl[0]["location"]["voivodeship"], "małopolskie")
        self.assertEqual(pl[0]["type_hint"], "university")
        self.assertEqual(rec["region"]["voivodeships"], ["małopolskie"])
        self.assertEqual(rec["funding"]["currency"], "EUR")
        self.assertIsInstance(rec["funding"]["total_value"], float)
        self.assertEqual(rec["extra"]["category"], "projekty")
        self.assertEqual(rec["quality"]["status"], "ok")
        self.assertIn("Cel projektu", rec["text_for_llm"])
        json.dumps(rec, ensure_ascii=False)

    def test_harvest_conditional_download_and_offline(self):
        opener = FakeOpener(fixture_zip())

        def downloader(url, dest, **kw):
            return download_if_changed(url, dest, opener=opener, retries=0, **kw)

        with tempfile.TemporaryDirectory() as tmp:
            store = cordis.RawStore(Path(tmp))
            stats = cordis.HarvestStats()
            recs = list(cordis.harvest(store, programmes=("HORIZON",), downloader=downloader, today=TODAY, stats=stats))
            self.assertEqual(len(recs), 2)
            self.assertTrue(stats.files["HORIZON"]["changed"])
            # second run: the saved ETag is sent, server answers 304, file is read from disk
            stats2 = cordis.HarvestStats()
            recs2 = list(cordis.harvest(store, programmes=("HORIZON",), downloader=downloader, today=TODAY, stats=stats2))
            self.assertFalse(stats2.files["HORIZON"]["changed"])
            self.assertEqual(opener.requests[-1].get_header("If-none-match"), '"abc"')
            self.assertEqual([r["content_hash"] for r in recs], [r["content_hash"] for r in recs2])
            # offline and limit
            recs3 = list(cordis.harvest(store, programmes=("HORIZON",), offline=True, limit=1, today=TODAY))
            self.assertEqual(len(recs3), 1)
            self.assertEqual(len(opener.requests), 2)

    def test_offline_without_saved_dump(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                list(cordis.harvest(cordis.RawStore(Path(tmp)), programmes=("HORIZON",), offline=True))

    def test_format_changed(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("project.csv", "id;title\n1;x\n")
        with self.assertRaises(cordis.FormatChanged):
            cordis.read_dump(buf.getvalue())


if __name__ == "__main__":
    unittest.main()
