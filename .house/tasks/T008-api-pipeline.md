---
id: T008
title: API i pełny pipeline
status: todo
owner: null
branch: null
depends_on: [T004, T007]
capabilities: [python]
review: always
acceptance:
  - id: AC-1
    run: "cd app && RADAR_LLM=demo python -m pytest -q tests/test_api.py"
  - id: AC-2
    run: "RADAR_LLM=demo python scripts/run_use_case.py uc1 --via-api"
    expect: "pathway: transfer"
  - id: AC-3
    run: "RADAR_LLM=demo python scripts/run_use_case.py uc2 --via-api"
    expect: "pathway: akceleracja"
  - id: AC-4
    run: "docker compose up -d --build && python scripts/smoke.py --url http://localhost:8000; rc=$?; docker compose down; exit $rc"
    expect: "golden path OK"
    timeout: 900
protected:
  - app/tests/test_api.py
---
## Objective
A FastAPI app (`app/radar/api.py`) that exposes the whole flow and persists it, so the frontend and the
E2E tests drive one real pipeline.

## Context
- Endpoints (JSON, models from T001): `POST /submissions` (form text + consent) → card;
  `POST /scan` → candidates; `POST /candidates/{id}/card`; `GET/PATCH /innovations/{id}`;
  `POST /innovations/{id}/verify`; `GET /innovations/{id}/similar`; `POST /innovations/{id}/assessment`;
  `PATCH /innovations/{id}/assessment/{criterion}` (human override); `GET /innovations/{id}/pathway?explain=1`;
  `GET /innovations/{id}/matches`; `GET /metrics`; `GET /needs`, `POST /needs` (institution reports a
  problem); `GET /innovations?type=&institution=&status=`; `GET /export.csv`; `GET /health` (reports LLM mode).
- Store: SQLite file (`RADAR_DB`, default `data/radar.db`), loaded from seed on first start; `org_id` on
  every row; simple header `X-Org` for tenancy (no auth for the hackathon, documented as such).
- Errors from the LLM layer become 503 with a Polish message the UI can show; nothing hangs.
- OpenAPI served at `/docs`: that is the "integration with existing systems" answer for the jury, plus CSV export.
- `run_use_case.py --via-api` uses `fastapi.testclient` to walk the full flow.
- `scripts/smoke.py --url <base>` (stdlib only, so it runs on the host without installs): `/health`, then UC1
  and UC2 over HTTP, prints `golden path OK`. The container seeds its database on first start, so a fresh
  `docker compose up` shows a full radar.

## Out of scope
Frontend, deploy, authentication.
