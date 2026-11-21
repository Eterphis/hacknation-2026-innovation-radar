---
id: T024
title: "link: łańcuch dowodów i dojrzałość z klastra"
status: todo
owner: null
branch: null
depends_on: [T023]
capabilities: []
acceptance:
  - id: AC-1
    run: "cd app && .venv/Scripts/python -m pytest -q"
    timeout: 600
  - id: AC-2
    run: "cd app && .venv/Scripts/python -m pytest -q tests/test_link.py"
    timeout: 600
  - id: AC-3
    manual: "przypadek demo „technologia z uczelni”: artykuł + patent EP tej samej uczelni połączone, dojrzałość tech_ready z linkami do obu dowodów"
protected:
  - app/tests/test_pipeline.py
---
## Objective
Etap `link` zapisuje powiązania publikacja ↔ projekt ↔ patent ↔ inwestycja Kohesio (relacje OpenAIRE, wspólny org_id, podobieństwo opisu, kolejność w czasie) z pewnością; `maturity` liczy poziom z całego łańcucha i podaje `evidence_ids`; `hidden` = tech_ready+ bez śladu wdrożenia poza instytucją.

## Context
`pipeline-design.md` §6 i §8, stuby `link` i `maturity_for` w `app/radar/pipeline/tasks.py`. Sygnały z role=evidence trafiają tu bezpośrednio po normalize (T020).

## Out of scope
Duplikaty (T025).
