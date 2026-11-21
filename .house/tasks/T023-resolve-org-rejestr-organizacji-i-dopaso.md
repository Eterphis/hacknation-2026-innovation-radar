---
id: T023
title: "resolve_org: rejestr organizacji i dopasowanie afiliacji"
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
    run: "cd app && .venv/Scripts/python -m pytest -q tests/test_resolve_org.py"
    timeout: 600
  - id: AC-3
    manual: "na 40 ręcznie oznaczonych afiliacjach trafność >= 0.85, wynik w .house/experiments.csv"
protected:
  - app/tests/test_pipeline.py
---
## Objective
Tabela `organizations` (org_id, ids{ror,regon,nip,krs,wikidata,teryt}, type, is_public, region, aliases) ładowana z RAD-on `/opendata/polon/institutions` i ROR; etap `resolve_org` dzieli afiliacje, ujednolica nazwy i dopasowuje kaskadowo (id → alias → rozmyte + miasto) z pewnością i progami 0.90/0.70. LLM tylko jako wybór z 5 kandydatów. Wynik: org_id, is_public, region, institution_type (wejście dla gate).

## Context
`pipeline-design.md` §1 i §4, `data-access.md` (RAD-on: REGON/NIP/KRS/rodzaj/województwo; OpenAIRE i Kohesio: Wikidata). Stub: `app/radar/pipeline/tasks.py::resolve_org`.

## Out of scope
RSPO i GUS BIR (brak dostępu bez klucza); szkoły zostają luką.
