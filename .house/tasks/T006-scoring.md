---
id: T006
title: Karta oceny z uzasadnieniem
status: todo
owner: null
branch: null
depends_on: [T003, T005]
capabilities: [python, claude-api]
review: always
acceptance:
  - id: AC-1
    run: "cd app && RADAR_LLM=demo python -m pytest -q tests/test_scoring.py"
  - id: AC-2
    run: "python scripts/validate_rubric.py app/radar/scoring/rubric.yaml"
    expect: "rubric OK"
  - id: AC-3
    run: "RADAR_LLM=demo python scripts/run_use_case.py uc1 --until assessment"
    expect: "zapotrzebowanie: 5"
protected:
  - app/tests/test_scoring.py
  - app/radar/scoring/rubric.yaml
---
## Objective
Step c): an `Assessment` for a card with six criteria, each with level 1–5 (or null = "brak danych"),
justification, evidence quote and source, reproducible in demo mode and overridable by a human.

## Context
- Rubric: `.house/PLAN.md` §3.2, written as `app/radar/scoring/rubric.yaml` (criterion id, question, level
  descriptions 1–5, signals, pathway weights). The rubric file is the single source: UI and docs render it.
- Hybrid engine in `app/radar/scoring/engine.py`:
  - deterministic signals first: `zapotrzebowanie` from matching needs count, `nowosc` from T005 top
    similarity, `dojrzalosc` from stage, `przenaszalnosc` partly from cost and dependencies;
  - LLM (effort `medium`) only fills levels it can justify from the card text and writes the justification,
    quoting evidence; it never invents numbers; null when no evidence.
- Human override: `PATCH` stores the new level, who, why; the original AI level stays visible.
- Expected values for UC1 and UC2 are in `.house/demo-flow.md`; tests check them in demo mode and check
  that every criterion has justification + (evidence or null).

## Out of scope
Pathway choice, UI.
