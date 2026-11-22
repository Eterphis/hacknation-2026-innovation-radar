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
    # stage latency histogram, every LLM call (here the offline extractor), alert inputs
    assert 'radar_stage_duration_seconds_bucket{stage="gate",le="+Inf"}' in body
    assert 'radar_stage_duration_seconds_count{stage="score"}' in body
    assert 'radar_llm_requests_total{provider="mock",model="heuristic-v1",purpose="extract",outcome="ok"}' in body
    assert "# TYPE radar_llm_latency_seconds histogram" in body and "# TYPE radar_llm_cost_usd_total counter" in body
    assert "# TYPE radar_source_schedule_seconds gauge" in body
    counts = [float(l.split()[-1]) for l in body.splitlines() if l.startswith('radar_stage_duration_seconds_bucket{stage="gate"')]
    assert counts == sorted(counts) and counts[-1] >= 20  # cumulative buckets


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


def test_cost_rule_metrics_and_dashboard():
    """#13: share of cards without a large LLM, pregen state, cloud flag; every metric on the cost panel exists."""
    import re
    from pathlib import Path

    for src in ("demo-zgloszenia", "demo-kohesio", "demo-publikacje"):
        harvest.apply((src,)).get()
    from radar.api.main import app

    with TestClient(app) as c:
        body = c.get("/metrics").text
    assert "radar_cards_without_large_llm_ratio 1.0" in body  # demo: rules/mock only
    assert 'radar_cards_by_llm_path{path="cloud"} 0' in body
    assert re.search(r'radar_pregen_cards\{state="current"\} [1-9]', body) and 'radar_pregen_cards{state="missing"} 0' in body
    assert "radar_llm_cloud_allowed 0" in body and 'radar_pregen_slogans{by="reguły"}' in body
    dash = json.loads((Path(__file__).resolve().parents[2] / "deploy/observability/grafana/dashboards/costs.json").read_text("utf-8"))
    used = {m for p in dash["panels"] for t in p["targets"] for m in re.findall(r"radar_[a-z_]+", t["expr"])}
    exported = set(re.findall(r"^# TYPE (radar_[a-z_]+)", body, re.M))
    assert used <= exported, used - exported


def test_llm_path_counts_cloud_agent():
    from types import SimpleNamespace as N

    from radar.observability import llm_path

    assert llm_path(N(provenance={"provider": "mock"}, assessment={})) == "rules"
    assert llm_path(N(provenance={"provider": "local"}, assessment={"agent": {"provider": None}})) == "local"
    assert llm_path(N(provenance={"provider": "local"}, assessment={"agent": {"provider": "anthropic"}})) == "cloud"
