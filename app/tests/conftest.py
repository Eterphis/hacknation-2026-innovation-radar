import os
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_DATABASE_URL", f"sqlite:///{tmp_path / 'radar.db'}")
    monkeypatch.setenv("RADAR_EAGER", "1")
    monkeypatch.setenv("RADAR_LLM_PROVIDERS", "mock")
    monkeypatch.setenv("RADAR_SOURCES_FILE", str(APP / "sources.yaml"))
    monkeypatch.setenv("RADAR_DEMO_MODE", "1")  # tests run on the synthetic snapshots, never on the network
    monkeypatch.setenv("RADAR_ORG_REGISTRY", str(tmp_path / "no-registry.jsonl"))  # never the real data/ dir
    from radar.config import get_settings
    from radar.db import create_all, reset_engine

    get_settings.cache_clear()
    reset_engine()
    from radar.pipeline.celery_app import app

    app.conf.task_always_eager = True
    import radar.llm.router as r

    r._router = None
    from radar.basal import classifier

    classifier._head_cache.update(w=None, at=None)  # module cache must not carry a head across test databases
    from radar.basal import graph

    graph.reset_threshold()  # nor the corpus-adaptive graph threshold
    from radar.api import cache

    cache.reset_api_cache()  # nor cached API answers (radar.api.cache: /api/match, /api/ideas, /api/clusters)
    cache.VERSION_TTL = 0.0  # tests change data and read it back at once
    create_all()
    yield
    reset_engine()
