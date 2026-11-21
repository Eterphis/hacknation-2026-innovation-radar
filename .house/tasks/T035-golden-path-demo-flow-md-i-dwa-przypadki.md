---
id: T035
title: "Golden path: demo-flow.md i dwa przypadki demo"
status: todo
owner: null
branch: null
depends_on: [T026]
capabilities: []
acceptance:
  - id: AC-1
    run: "cd app && .venv/Scripts/python -m pytest -q"
    timeout: 600
  - id: AC-3
    manual: "scenariusz a-e z treści zadania przechodzi na obu przypadkach (uczelnia: artykuł + patent EP bez wdrożenia; gmina z Kohesio do przeniesienia) w UI bez kluczy"
protected:
  - app/tests/test_pipeline.py
---
## Objective
`.house/demo-flow.md` z ponumerowanymi krokami i oczekiwanym ekranem po każdym; dane dla dwóch przypadków (D-008 pkt 4) w `app/samples/` (z prawdziwych rekordów z atrybucją albo wyraźnie oznaczone jako przykładowe); UI prowadzi przez scenariusz a-e.

## Context
D-008, `.house/playbooks/build.md` (Flow 3); dziś w `app/samples/` są dane syntetyczne oznaczone [DANE SYNTETYCZNE].

## Out of scope
Pitch i film.

## Stan (2026-11-21, sesja app/Helm)
UI: strona „Przegląd” odpowiada na pytania biznesowe (trendy, wyróżniające się, zaawansowane, gotowe do powielenia, tanie, wymagające budżetu, perełki, dublowanie, luki regionalne). Zostało: demo-flow.md i dwa prawdziwe przypadki.
