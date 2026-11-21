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
