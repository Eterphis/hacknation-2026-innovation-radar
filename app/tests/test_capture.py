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


def test_guides_tell_the_story_from_facts_without_a_model():
    from radar.api.main import app
    from radar.pipeline.tasks import harvest

    harvest.apply(("demo-zgloszenia",)).get()
    with TestClient(app) as c:
        g = c.get("/api/guides").json()
        assert {x["key"] for x in g} == {"radek", "ada", "tomek", "ola", "profesor"}
        cid = c.get("/api/ideas?limit=1").json()["items"][0]["card_id"]
        for k in ("radek", "ada", "tomek", "ola", "profesor"):
            p = c.get(f"/api/cards/{cid}/pitch", params={"guide": k}).json()
            assert p["by"] == "reguły" and p["text"].startswith("Cześć") and len(p["text"]) > 80
        assert c.get(f"/api/cards/{cid}/pitch", params={"guide": "ada"}).json()["cached"] is True
        assert c.get(f"/api/cards/{cid}/pitch", params={"guide": "nikt"}).status_code == 404


def test_model_text_with_invented_numbers_is_rejected():
    from radar.api.guides import validate

    src = "Projekt kosztuje około 137 tysięcy złotych, odbiorców jest 950."
    ok = "Ten projekt kosztuje około 137 tysięcy złotych i może pomóc 950 szpitalom w całej Polsce, bo działa już w praktyce."
    assert validate(ok, src) == ok
    assert validate(ok.replace("950", "1200"), src) is None
    assert validate("Za krótko.", src) is None


def test_spoken_amounts_use_polish_plurals():
    from radar.api.guides import zl

    assert [zl(50e6), zl(1.6e6), zl(2e6), zl(1e6), zl(137220), zl(22000), zl(1000)] == [
        "50 milionów złotych", "1,6 miliona złotych", "2 miliony złotych", "1 milion złotych",
        "137 tysięcy złotych", "22 tysiące złotych", "1 tysiąc złotych"]


def test_small_model_bad_json_falls_back_to_rules(monkeypatch):
    """A 1.5B model answering bare strings (seen live with Bielik) must not stall a record: rules make the card."""
    from radar.llm.router import router as real_router
    from radar.pipeline import extract as ex

    real = real_router()

    class P:
        def __init__(self, name):
            self.name = name

    class Stub:
        providers = [P("local"), P("mock")]

        def complete_json(self, system, user, purpose="other", exclude=(), **kw):
            if "local" not in exclude:
                return {"is_innovation": "tak", "solution_name": "Drony", "innovation_type": "edukacyjna"}, {"provider": "local", "model": "bielik"}
            return real.complete_json(system, user, purpose=purpose)

    monkeypatch.setattr(ex, "router", lambda: Stub())
    text = ex.source_text("Szkolne drony do inspekcji dachów", "Uczniowie technikum budują drony z kamerą termowizyjną, które sprawdzają dachy szkół i urzędów gminy. Gmina oszczędza na podnośnikach.", ["drony"])
    out, errors, prov = ex.extract(text, max_retries=1)
    assert out is not None and not errors
    assert prov["fallback_after"] == "local" and prov["model_errors"]


def test_pitch_never_generates_for_a_user(monkeypatch):
    """Public /pitch: never runs a model (stored narration or rule text); llm/fresh need the operator token."""
    from radar.api import guides
    from radar.api.main import app
    from radar.pipeline.tasks import harvest

    harvest.apply(("demo-zgloszenia",)).get()
    monkeypatch.setenv("RADAR_GUIDE_LLM_URL", "http://llm:8080/v1")
    calls = []
    monkeypatch.setattr(guides, "bielik", lambda text, g: (calls.append(g), ("Cześć, tu Ada. Krótka historia projektu bez nowych liczb, opowiedziana spokojnie i do końca, żeby walidacja ją przyjęła.", 0.1))[1])
    with TestClient(app) as c:
        cid = c.get("/api/ideas?limit=1").json()["items"][0]["card_id"]
        url = f"/api/cards/{cid}/pitch"
        assert c.get(url, params={"guide": "ada"}).json()["by"] == "reguły" and not calls  # no model for a user
        monkeypatch.setenv("RADAR_OPERATOR_TOKEN", "s3cret")
        assert c.get(url, params={"guide": "ada", "llm": True}).status_code == 401
        assert c.get(url, params={"guide": "ada", "fresh": True}).status_code == 401
        r = c.get(url, params={"guide": "ada", "fresh": True, "llm": True}, headers={"X-Operator-Token": "s3cret"})
        assert r.status_code == 200 and len(calls) == 1  # prepared in advance by the operator
        p = c.get(url, params={"guide": "ada"}).json()
        assert p["cached"] is True and len(calls) == 1  # users get the stored text
