import hashlib
import hmac
import json

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from radar.db import session
from radar.models import Card, RawRecord, Record, StageRun
from radar.pipeline.normalize import t_doi, t_pl_decimal
from radar.pipeline.tasks import harvest, reconcile_all
from radar.sources.oaipmh import parse_page
from radar.sources.registry import load_sources


def test_sources_yaml_is_valid():
    specs = load_sources()
    assert {"demo-publikacje", "demo-kohesio", "zgloszenia", "bibliotekanauki"} <= specs.keys()
    assert specs["przyklad-amqp"].mode == "push"


def test_transforms():
    assert t_pl_decimal(["336000000,00"]) == 336000000.0
    assert t_pl_decimal("1 234,5") == 1234.5
    assert t_doi(["https://doi.org/10.1/ABC", "x"]) == "10.1/abc"
    assert t_doi("doi:10.2/x") == "10.2/x"


def test_demo_publications_end_to_end():
    out = harvest.apply(("demo-publikacje",)).get()
    assert out["accepted"] == 4 and out["new"] == 4
    with session() as s:
        statuses = dict(s.execute(select(Record.status, func.count()).group_by(Record.status)).all())
        assert statuses.get("duplicate") == 1, statuses  # same DOI, different case/prefix
        assert statuses.get("not_innovation") == 1, statuses  # history article, no signal words
        assert statuses.get("ready") == 2, statuses
        card = s.scalar(select(Card).join(Record).where(Record.title.contains("kompozytów")))
        assert card.maturity == "tech_ready"  # pilot described
        assert card.provenance["provider"] == "mock"
        assert all(e["quote"] for e in card.evidence.values())


def test_reharvest_is_idempotent():
    harvest.apply(("demo-publikacje",)).get()
    with session() as s:
        runs_before = s.scalar(select(func.count()).select_from(StageRun))
    again = harvest.apply(("demo-publikacje",)).get()
    assert again["unchanged"] == 4
    with session() as s:
        assert s.scalar(select(func.count()).select_from(StageRun)) == runs_before
    assert reconcile_all() == 0


def test_kohesio_amounts_and_maturity():
    harvest.apply(("demo-kohesio",)).get()
    with session() as s:
        rec = s.scalar(select(Record).where(Record.title.contains("wodorowe")))
        assert rec.amounts["amount_eu"] == 336000000.0
        assert rec.card.maturity == "business_ready"


def test_webhook_and_manual_submission(monkeypatch):
    from radar.api.main import app

    c = TestClient(app)
    body = json.dumps({"id": "ext-1", "title": "System zapisów do przedszkoli",
                       "description": "Opracowano system zapisów online, który skraca kolejki w urzędzie gminy i "
                                      "upraszcza procedurę dla rodziców.", "institution": "Gmina X"}).encode()
    monkeypatch.setenv("RADAR_WEBHOOK_SECRET_ZGLOSZENIA", "s3cret")
    assert c.post("/api/ingest/webhook/zgloszenia", content=body).status_code == 401
    sig = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    r = c.post("/api/ingest/webhook/zgloszenia", content=body, headers={"X-Radar-Signature": sig})
    assert r.status_code == 202 and r.json()["new"] == 1
    r = c.post("/api/ingest/webhook/zgloszenia", content=body, headers={"X-Radar-Signature": sig})
    assert r.json()["unchanged"] == 1

    r = c.post("/api/ingest/zgloszenia/manual", json={
        "title": "Gminny bank sprzętu rehabilitacyjnego",
        "description": "Problem: mieszkańcy czekają miesiącami na sprzęt. Opracowano model wypożyczalni prowadzonej "
                       "przez ośrodek pomocy społecznej we współpracy z organizacjami pozarządowymi.",
        "institution": "Gmina Y", "institution_type": "JST"})
    assert r.status_code == 202
    cards = c.get("/api/cards").json()
    assert len(cards) == 2
    d = c.post(f"/api/cards/{cards[0]['id']}/decision", json={"decision": "approved"}).json()
    assert d["decision"] == "approved"
    with session() as s:
        vias = set(s.scalars(select(RawRecord.received_via)))
    assert vias == {"webhook", "upload"}


def test_oai_parser():
    xml = """<?xml version="1.0"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><ListRecords>
    <record><header><identifier>oai:x:1</identifier><datestamp>2026-10-22</datestamp><setSpec>j1</setSpec></header>
    <metadata><oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title xml:lang="pl">Tytuł</dc:title><dc:title xml:lang="en">Title</dc:title><dc:creator>A, B</dc:creator>
    </oai_dc:dc></metadata></record>
    <record><header status="deleted"><identifier>oai:x:2</identifier><datestamp>2026-10-23</datestamp></header></record>
    <resumptionToken>tok123</resumptionToken></ListRecords></OAI-PMH>"""
    recs, token, _ = parse_page(xml)
    assert token == "tok123"
    (r1, d1), (r2, d2) = recs
    assert r1["title"] == ["Tytuł", "Title"] and r1["title_en"] == ["Title"] and not d1
    assert d2 and r2["oai_identifier"] == "oai:x:2"
