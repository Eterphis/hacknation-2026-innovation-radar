"""Reliable capture: RSS with conditional GET, submissions never vanish, no overlapping harvests."""

import json

import httpx
import respx
from fastapi.testclient import TestClient

from radar.sources.base import SourceSpec
from radar.sources.rss import RssConnector, parse_feed

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>
<item><title>Szkolna pracownia dronow dla gmin</title><link>https://ex.pl/1</link><guid>g1</guid>
<description>&lt;p&gt;Uczniowie technikum buduja drony do inspekcji dachow budynkow gminnych.&lt;/p&gt;</description><pubDate>Sat, 21 Nov 2026 10:00:00 GMT</pubDate></item>
<item><title>Aplikacja kolejki do lekarza</title><link>https://ex.pl/2</link><guid>g2</guid><description>Szpital powiatowy</description></item>
</channel></rss>"""
ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>a1</id><title>Pomysl</title><link href="https://ex.pl/a1"/>
<summary>Opis pomyslu</summary><updated>2026-11-20T10:00:00Z</updated></entry></feed>"""


def test_parse_rss_and_atom():
    items = parse_feed(RSS)
    assert [i["id"] for i in items] == ["g1", "g2"] and items[0]["year"] == 2026 and "<p>" not in items[0]["description"]
    assert parse_feed(ATOM)[0]["url"] == "https://ex.pl/a1"


@respx.mock
def test_rss_only_new_entries_and_304_costs_nothing():
    spec = SourceSpec(id="rss-t", type="rss", options={"feeds": ["https://ex.pl/feed"], "min_interval_s": 0})
    route = respx.get("https://ex.pl/feed")
    route.mock(return_value=httpx.Response(200, content=RSS, headers={"ETag": '"v1"'}))
    pages = list(RssConnector(spec).fetch(None))
    assert sum(len(p.items) for p in pages) == 2
    cursor = pages[-1].next_cursor
    # unchanged feed: server answers 304 to our If-None-Match
    route.mock(side_effect=lambda req: httpx.Response(304) if req.headers.get("If-None-Match") == '"v1"' else httpx.Response(200, content=RSS))
    pages2 = list(RssConnector(spec).fetch(cursor))
    assert pages2[0].meta.get("not_modified") and not pages2[0].items
    # changed feed without ETag: only the new entry is ingested
    route.mock(return_value=httpx.Response(200, content=RSS.replace(b"<guid>g2</guid>", b"<guid>g3</guid>")))
    st = json.loads(cursor); st["https://ex.pl/feed"].pop("etag")
    pages3 = list(RssConnector(spec).fetch(json.dumps(st)))
    assert [e.external_id for p in pages3 for e in p.items] == ["g3"]


@respx.mock
def test_broken_feed_does_not_stop_others():
    spec = SourceSpec(id="rss-t", type="rss", options={"feeds": ["https://bad.pl/f", "https://ok.pl/f"], "min_interval_s": 0})
    respx.get("https://bad.pl/f").mock(return_value=httpx.Response(404))
    respx.get("https://ok.pl/f").mock(return_value=httpx.Response(200, content=ATOM))
    pages = list(RssConnector(spec).fetch(None))
    assert pages[0].meta.get("error") and len(pages[1].items) == 1


def test_submission_is_tracked_and_never_silently_rejected():
    from radar.api.main import app

    with TestClient(app) as c:
        # short and vague: Basal would normally hold or reject this; a person's submission must still get a card
        r = c.post("/api/ingest/zgloszenia/manual", json={"title": "Pomysł jury: wspólny kalendarz zajęć dla szkół w gminie",
                   "description": "Gminy i szkoły publikują zajęcia pozalekcyjne w jednym kalendarzu, rodzice zapisują dzieci online, a dyrektorzy widzą obłożenie sal. Działa od roku w jednej gminie.",
                   "institution": "Szkoła Podstawowa nr 1", "institution_type": "szkola", "region": "podkarpackie"}).json()
        assert r["new"] == 1 and r["track"].endswith(str(r["raw_id"]))
        st = c.get(r["track"]).json()
        assert st["record_status"] not in ("rejected",) and st["card_id"], st
        assert {s["stage"] for s in st["stages"]} >= {"gate", "score"}
        assert c.get("/api/submissions/999999").status_code == 404


def test_harvest_skips_when_same_source_is_running():
    from datetime import datetime, timezone

    from radar.db import session
    from radar.models import SourceState
    from radar.pipeline.tasks import harvest

    with session() as s:
        s.merge(SourceState(source_id="demo-publikacje", counters={}, last_status="running", last_run_at=datetime.now(timezone.utc)))
    assert harvest.apply(("demo-publikacje",)).get() == {"skipped": "already running"}


def test_operator_actions_need_token_when_configured(monkeypatch):
    from radar.api.main import app

    monkeypatch.setenv("RADAR_OPERATOR_TOKEN", "s3cret")
    with TestClient(app) as c:
        assert c.post("/api/basal/train").status_code == 401
        assert c.post("/api/cards/1/decision", json={"decision": "approved"}).status_code == 401
        assert c.post("/api/sources/demo-publikacje/run").status_code == 401
        assert c.post("/api/basal/train", headers={"X-Operator-Token": "s3cret"}).status_code != 401
        # reading, matching and submitting stay open
        assert c.get("/api/ideas").status_code == 200
