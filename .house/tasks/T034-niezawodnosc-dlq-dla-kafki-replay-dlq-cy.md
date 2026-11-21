---
id: T034
title: "Niezawodność: DLQ dla Kafki, replay DLQ, cykliczny reconcile, liczniki w UI"
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
    run: "cd app && .venv/Scripts/python -m pytest -q tests/test_reliability.py"
    timeout: 600
protected:
  - app/tests/test_pipeline.py
---
## Objective
Kafka: nieudane wiadomości do `<topic>.dlq`; `radar replay-dlq <queue>` przenosi wiadomości z `<stage>.dlq` z powrotem; `reconcile` jako CronJob w Helm; ekran Liczniki pokazuje uzgodnienie przyjęte = gotowe + przegląd + odrzucone + w toku + DLQ (D-005).

## Context
`app/radar/sources/push.py` (TODO T034), `app/radar/pipeline/tasks.py::reconcile_all`, `app/radar/pipeline/celery_app.py` (DLX), `app/radar/api/static/index.html`.

## Out of scope
Zmiana brokera.
