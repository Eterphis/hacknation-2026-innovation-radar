import json
import logging

from fastapi.testclient import TestClient

from radar.observability import JsonFormatter
from radar.pipeline.tasks import harvest


def test_metrics_exposition():
    harvest.apply(("demo-zgloszenia",)).get()
    from radar.api.main import app

    with TestClient(app) as c:
        r = c.get("/metrics")
    assert r.status_code == 200
    body = r.text
    for name in ("radar_stage_runs_total", "radar_records", "radar_cards", "radar_llm_extractions_total", "radar_queue_messages"):
        assert f"# TYPE {name}" in body
    assert 'radar_stage_runs_total{stage="gate",outcome="ok"}' in body
    assert 'radar_source_last_accepted{source="demo-zgloszenia"} 20' in body


def test_json_log_line():
    rec = logging.LogRecord("radar", logging.INFO, __file__, 1, "harvest %s", ("x",), None)
    rec.stage, rec.raw_id = "gate", 7
    d = json.loads(JsonFormatter().format(rec))
    assert d["msg"] == "harvest x" and d["stage"] == "gate" and d["raw_id"] == 7


def test_static_assets_served():
    from radar.api.main import app

    with TestClient(app) as c:
        assert c.get("/").headers["cache-control"] == "no-cache"
        assert "i-map-pin" in c.get("/static/icons.svg").text
        pl = c.get("/static/poland.json").json()
        assert len(pl["regions"]) == 16
