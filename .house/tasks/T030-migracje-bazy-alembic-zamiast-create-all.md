---
id: T030
title: "Migracje bazy (Alembic) zamiast create_all"
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
    run: "cd app && .venv/Scripts/python -m alembic upgrade head"
    timeout: 600
protected:
  - app/tests/test_pipeline.py
---
## Objective
Schemat bazy w migracjach Alembic; `radar initdb` uruchamia `alembic upgrade head`; Job Helm i start API przestają wołać `create_all`.

## Context
`app/radar/db.py`, `app/radar/api/main.py` (lifespan), `deploy/helm/innovation-radar/templates/backing.yaml` (Job migrate).

## Out of scope
Zmiany modelu danych (każde zadanie dodaje własną migrację).
