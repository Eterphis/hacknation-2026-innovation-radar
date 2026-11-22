"""Liczba zapytań SQL i czas na żądanie dla endpointów z testu obciążeniowego (profilowanie, issue #31).

Uruchomienie (bez sieci, SQLite + dane demo):
    cd app && .venv/Scripts/python ../loadtest/sql_profile.py
Zdarzenie SQLAlchemy `before_cursor_execute` liczy każde zapytanie wysłane do bazy w czasie jednego żądania.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ.update(RADAR_DATABASE_URL=f"sqlite:///{tmp / 'p.db'}", RADAR_EAGER="1", RADAR_DEMO_MODE="1", RADAR_LLM_PROVIDERS="mock",
                  RADAR_LOG_LEVEL="WARNING", RADAR_ORG_REGISTRY=str(tmp / "none.jsonl"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402

from radar.cli import main as cli  # noqa: E402

cli(["demo"])
from radar.api.main import app  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

COUNT = {"n": 0}
event.listen(Engine, "before_cursor_execute", lambda *a, **k: COUNT.__setitem__("n", COUNT["n"] + 1))

PATHS = ["/api/match?role=samorzady&voivodeship=pomorskie&budget=wysoki&limit=24", "/api/match?role=inwestorzy&limit=24",
         "/api/ideas?limit=24", "/api/ideas?maturity=business_ready,market_ready&limit=24", "/api/clusters?mode=tematy",
         "/api/clusters?mode=rynki", "/api/cards/1", "/api/cards/9"]
with TestClient(app) as c:
    print(f"{'endpoint':70} {'1. wyw.':>14} {'2. wyw.':>14}")
    for p in PATHS:
        row = []
        for _ in range(2):
            COUNT["n"] = 0
            t = time.perf_counter()
            assert c.get(p).status_code == 200
            row.append(f"{COUNT['n']:4d} SQL {1000 * (time.perf_counter() - t):5.0f} ms")
        print(f"{p:70} {row[0]:>14} {row[1]:>14}")
