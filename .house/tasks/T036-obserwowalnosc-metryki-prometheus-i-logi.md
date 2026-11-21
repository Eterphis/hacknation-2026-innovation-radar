---
id: T036
title: "Obserwowalność: metryki Prometheus i logi strukturalne"
status: todo
owner: null
branch: null
depends_on: []
capabilities: []
acceptance:
  - id: AC-1
    run: "cd app && .venv/Scripts/python -m pytest -q"
    timeout: 600
  - id: AC-2
    run: "cd app && .venv/Scripts/python -c \"from fastapi.testclient import TestClient; from radar.api.main import app; print(TestClient(app).get('/metrics').status_code)\""
    timeout: 600
    expect: "200"
protected:
  - app/tests/test_pipeline.py
---
## Objective
`/metrics` z licznikami etapów, długością kolejek, czasem i kosztem wywołań LLM per dostawca i fallbackami; logi JSON z `raw_id`, `stage`, `source_id`; adnotacje scrape w Helm.

## Context
`app/radar/api/main.py`, `app/radar/llm/router.py` (provenance z fallbackami).

## Out of scope
Dashboardy Grafany.
