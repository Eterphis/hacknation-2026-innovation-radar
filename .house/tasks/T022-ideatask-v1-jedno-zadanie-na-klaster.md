---
id: T022
title: "IdeaTask v1: jedno zadanie na klaster"
status: todo
owner: null
branch: null
depends_on: [T021, T025]
capabilities: []
acceptance:
  - id: AC-1
    run: "cd app && .venv/Scripts/python -m pytest -q"
    timeout: 600
  - id: AC-2
    run: "cd app && .venv/Scripts/python -m pytest -q tests/test_ideatask.py"
    timeout: 600
protected:
  - app/tests/test_pipeline.py
---
## Objective
Po `gate` z wynikiem pass powstaje albo aktualizuje się jeden `IdeaTask` (schemat §6) na `cluster_id`, z sygnałami wszystkich źródeł klastra. `extract`/`analyze` pracują na zadaniu, karta innowacji jest jedna na klaster.

## Context
`sources-and-idea-flow.md` §6, D-007 (klastry z dedup), `app/radar/models.py` (Card ma dziś record_id), API `/api/cards`.

## Out of scope
Feed, głosowanie, propozycje. Golden path może działać per rekord (T021).
