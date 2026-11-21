---
id: T001
title: Kontrakt danych i szkielet repo
status: todo
owner: null
branch: null
depends_on: []
capabilities: [python]
review: always
acceptance:
  - id: AC-1
    run: "grep -q 'EUROPEAN UNION PUBLIC LICENCE v. 1.2' LICENSE"
  - id: AC-2
    run: "cd app && python -m pytest -q tests/test_contract.py"
    timeout: 300
  - id: AC-3
    run: "python scripts/export_schema.py --check"
  - id: AC-4
    run: "test -f .env.example && test -z \"$(git ls-files .env)\""
  - id: AC-5
    run: "python -c \"import tomllib;d=tomllib.load(open('app/pyproject.toml','rb'));assert d['project']['license']=='EUPL-1.2'\""
  - id: AC-6
    run: "docker compose up -d --build && curl -fsS --retry 30 --retry-connrefused --retry-delay 2 http://localhost:8000/health; rc=$?; docker compose down; exit $rc"
    timeout: 900
  - id: AC-7
    run: "docker compose run --rm app test"
    timeout: 900
protected:
  - app/tests/test_contract.py
---
## Objective
Repo has the skeleton every later task builds on, and the data contract is fixed: Pydantic models in
`app/radar/models.py` for `InnovationCard`, `SourceRef`, `Assessment` (with `CriterionScore`),
`SimilarItem`, `Pathway`, `Recipient`, `Need`, `Match`, `Metrics`, `Candidate`; a JSON Schema export in
`schema/contract.schema.json` that the frontend generates TypeScript types from. From this task on the app
starts with one command, `docker compose up --build`, and answers `GET /health`.

## Context
- Field list: `.house/PLAN.md` §3.1 (card), §3.2 (criteria: dojrzalosc, zapotrzebowanie, nowosc,
  przenaszalnosc, wplyw, gotowosc), §3.3 (pathway ids: transfer, komercjalizacja, grant, akceleracja,
  pilotaz, doprecyzuj), §3.4 (metrics).
- Enums: innovation type (technologiczna, organizacyjna, edukacyjna, spoleczna, procesowa; a card may have
  several), institution type (szkola, uczelnia, jst, inna_publiczna), stage (pomysl, prototyp, pilotaz,
  wdrozone, powielone), channel (formularz, wykrycie), status (kandydat, karta, zweryfikowana, oceniona,
  skierowana).
- Every AI-filled field carries provenance: `{value, source: SourceRef|None, by: "ai"|"human", confidence}`.
  `SourceRef` = url or document id + quoted span + retrieved_at. Example records have `example: true`.
- `CriterionScore` = criterion, level 1–5 or null ("brak danych"), justification, evidence quote, source,
  confidence, overridden_by_human.
- Multi-tenant from day one: every record has `org_id` (institution or operator), see PLAN §6.
- Layout: `app/` (pyproject, package `radar`, `tests/`), `web/` (empty placeholder, T009), `data/`,
  `scripts/`, `docs/`, `pitch/`, `schema/`. `LICENSE` = official EUPL-1.2 text (e.g. SPDX
  `license-list-data/text/EUPL-1.2.txt`), `README.md` stub with licence and run commands,
  `.env.example` with `ANTHROPIC_API_KEY=`, `RADAR_LLM=demo`, `RADAR_MODEL=claude-opus-5-5`.
- Docker skeleton (PLAN §2 and §7 rule 8): multi-stage `Dockerfile` (stage `web` on `node:22-slim`
  building `web/` when it has a `package.json`, otherwise skipped with a placeholder page; stage `app` on
  `python:3.12-slim`, non-root user, dependencies installed in their own cached layer), `.dockerignore`,
  `docker-compose.yml` (service `app`, port 8000, `env_file` `.env` with `required: false`, named volume
  `radar-data` for `RADAR_DB`, healthcheck on `/health`, `RADAR_LLM` defaulting to `demo`),
  `docker-compose.dev.yml` (bind-mount `app/` and `web/`, uvicorn `--reload`, Vite on 5173), and
  `docker/entrypoint.sh` with subcommands `serve` (default), `test` (pytest), `seed`, `keycheck`.
  Minimal FastAPI `app/radar/api.py` with `GET /health` returning `{status, llm_mode, version}`; T008
  extends it. Line endings LF for shell scripts (`.gitattributes`), so the image builds on Windows too.
- Dependencies only MIT / BSD / Apache-2.0 (FastAPI, Pydantic, uvicorn, pytest, PyYAML, rank-bm25,
  anthropic).

## Out of scope
Any business logic (LLM calls, scoring, search). UI. Real data.
