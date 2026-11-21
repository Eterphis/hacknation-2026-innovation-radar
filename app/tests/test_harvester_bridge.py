"""Contract: records written by the team's harvester (radar/refresh.py, schema radar.record/v1) enter the app
pipeline through the `harvester-*` snapshot sources and come out as scored cards."""

import json

from sqlalchemy import select

from radar.db import session
from radar.models import Record
from radar.pipeline.tasks import harvest

NCBR_LIKE = {
    "schema": "radar.record/v1", "source": "ncbr_sukcesy", "record_id": "ncbr-demo-1", "url": "https://www.gov.pl/web/ncbr/x",
    "record_type": "funded_project_success_story", "language": "pl",
    "title": "Inteligentny system monitorowania jakości wody w sieciach wodociągowych gmin",
    "intro": "Opracowano system czujników i aplikację do monitorowania jakości wody.",
    "text_for_llm": "Problem: gminy wykrywają skażenia wody z opóźnieniem. Opracowano system czujników IoT i aplikację, "
                    "która w czasie rzeczywistym monitoruje jakość wody w sieci wodociągowej. Rozwiązanie przetestowano w "
                    "pilotażu w dwóch gminach województwa podkarpackiego i wdrożono u beneficjenta.",
    "organizations": [{"name": "Politechnika Rzeszowska", "role": "beneficiary"}, {"name": "Gmina Krasne", "role": "partner"}],
    "funding": {"operator": "NCBR", "total_value": 2450000.0, "grant_value": 1980000.0, "currency": "PLN"},
    "period": {"start": "2022-03-01", "end": "2024-12-31", "status": "finished"},
    "region": {"voivodeships": ["podkarpackie"], "nationwide": False},
    "keywords": ["woda", "IoT", "monitoring"],
    "rights": {"licence": "unknown", "llm_may_read_fulltext": True}, "quality": {"status": "ok"},
}


def test_harvester_output_flows_through_pipeline(tmp_path, monkeypatch):
    (tmp_path / "ncbr.jsonl").write_text(json.dumps(NCBR_LIKE, ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setenv("RADAR_HARVEST_DIR", str(tmp_path))
    out = harvest.apply(("harvester-ncbr",)).get()
    assert out["new"] == 1
    with session() as s:
        r = s.scalar(select(Record).where(Record.source_id == "harvester-ncbr"))
        assert r.title.startswith("Inteligentny system") and "IoT" in r.abstract
        assert r.affiliations == ["Politechnika Rzeszowska", "Gmina Krasne"]
        assert r.voivodeship == "podkarpackie" and r.year == 2022
        assert r.amounts["amount_total"] == 2450000.0
        assert r.status == "ready" and r.card.score is not None
        assert r.extra["harvester_source"] == "ncbr_sukcesy"


def test_missing_harvester_file_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_HARVEST_DIR", str(tmp_path))
    out = harvest.apply(("harvester-cordis",)).get()
    assert out["accepted"] == 0 and out["pages"] == 1


WEB_LIKE = {
    "schema": "radar.record/v1", "source": "web_ur_ctt", "source_name": "CTT Uniwersytetu Rzeszowskiego (strona www)",
    "record_id": "czujnik-gleby-0123456789", "url": "https://ctt.ur.edu.pl/aktualnosci/czujnik-gleby",
    "record_type": "web_news", "language": "pl", "title": "Bezprzewodowy czujnik wilgotności gleby dla gmin wiejskich",
    "intro": "Naukowcy opracowali tani czujnik wilgotności gleby.",
    "text": {"body": "...", "description": "Naukowcy opracowali tani czujnik wilgotności gleby."},
    "text_for_llm": "Tytuł: Bezprzewodowy czujnik wilgotności gleby dla gmin wiejskich\n\n"
                    "Naukowcy z Uniwersytetu Rzeszowskiego opracowali tani bezprzewodowy czujnik wilgotności gleby, który "
                    "pozwala gminom i rolnikom planować nawadnianie. Prototyp przetestowano na polach doświadczalnych, a "
                    "uczelnia szuka partnerów do wdrożenia rozwiązania w gminach województwa podkarpackiego. Czujnik działa "
                    "na baterii przez dwa lata i przesyła dane przez sieć LoRaWAN do aplikacji.",
    "organizations": [{"name": "Uniwersytet Rzeszowski", "role": "publisher"}],
    "funding": {"total_value": None, "grant_value": None}, "period": {"start": None},
    "region": {"voivodeships": ["podkarpackie"]}, "keywords": [],
    "extra": {"category": "nauka", "site_id": "ur_ctt", "published": "2026-10-02"},
    "rights": {"licence": "unknown"}, "quality": {"status": "ok"},
}


def test_web_crawler_export_flows_through_pipeline(tmp_path, monkeypatch):
    (tmp_path / "web.jsonl").write_text(json.dumps(WEB_LIKE, ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setenv("RADAR_HARVEST_DIR", str(tmp_path))
    out = harvest.apply(("harvester-web",)).get()
    assert out["new"] == 1
    with session() as s:
        r = s.scalar(select(Record).where(Record.source_id == "harvester-web"))
        assert r.title.startswith("Bezprzewodowy czujnik") and "LoRaWAN" in r.abstract
        assert r.affiliations == ["Uniwersytet Rzeszowski"] and r.voivodeship == "podkarpackie"
        assert r.extra["harvester_source"] == "web_ur_ctt"
        assert r.status == "ready"


def test_every_harvester_output_has_a_source():
    """Each file radar.refresh writes to data/normalized/ is picked up by exactly one harvester-* source."""
    from radar.sources.registry import load_sources

    paths = {s.options["path"].rsplit("/", 1)[-1]: s for s in load_sources().values() if s.id.startswith("harvester-")}
    expected = {"interreg", "ncbr", "web", "bibliotekanauki", "openalex", "radon", "epo", "cordis", "fe_projects",
                "uprp_import"}
    assert {f"{n}.jsonl" for n in expected} <= set(paths)
    assert all(s.mapping == paths["ncbr.jsonl"].mapping for s in paths.values())  # one shared &record_v1


def test_biblioteka_nauki_and_radon_have_one_path():
    """Issue #5: these came in twice (app connectors and the harvester); the harvester path is the one."""
    from radar.sources.registry import load_sources

    specs = load_sources()
    assert not specs["bibliotekanauki"].enabled and not specs["radon-projekty"].enabled
    assert specs["harvester-bibliotekanauki"].enabled and specs["harvester-radon"].enabled
