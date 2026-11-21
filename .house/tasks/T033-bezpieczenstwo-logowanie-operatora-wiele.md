---
id: T033
title: "Bezpieczeństwo: logowanie operatora, wiele organizacji, sekrety webhooków"
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
    run: "cd app && .venv/Scripts/python -m pytest -q tests/test_auth.py"
    timeout: 600
protected:
  - app/tests/test_pipeline.py
---
## Objective
Endpointy operatora (`/api/cards/*/decision`, `/api/sources/*/run`) wymagają uwierzytelnienia (OIDC albo token); karty mają organizację (tenant), operator widzi swoje; poza trybem demo webhook bez `RADAR_WEBHOOK_SECRET_<ID>` jest odrzucany; rate limit na `/api/ingest/*`; opis w README (treść §5: bezpieczeństwo, wiele organizacji).

## Context
`app/radar/api/main.py`, `app/radar/sources/push.py::verify_signature`.

## Out of scope
Konta publiczności do głosowania (feed, D-010).
