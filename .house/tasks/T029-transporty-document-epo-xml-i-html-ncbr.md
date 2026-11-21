---
id: T029
title: "Transporty document (EPO XML) i html (NCBR)"
status: todo
owner: null
branch: null
depends_on: [T020]
capabilities: []
acceptance:
  - id: AC-1
    run: "cd app && .venv/Scripts/python -m pytest -q"
    timeout: 600
  - id: AC-2
    run: "cd app && .venv/Scripts/python -m pytest -q tests/test_document_html.py"
    timeout: 600
protected:
  - app/tests/test_pipeline.py
---
## Objective
Typ `document`: pełny tekst po ID z rekordu (np. data.epo.org/linked-data/representation/publication/EP/<nr>/<kind>.xml → abstract, description, claims) dołączany do sygnału; typ `html`: lista + strony szczegółów z selektorami CSS w sources.yaml (NCBR wyszukiwarka sukcesów). Rejestracja przez `radar.sources.registry.register`.

## Context
`sources-and-idea-flow.md` §2 i §11 (kroki 4 i 7), `app/radar/sources/base.py`.

## Out of scope
Omijanie ochrony przed botami (UPRP) jest wykluczone.
