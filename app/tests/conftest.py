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
    create_all()
    yield
    reset_engine()
