---
id: T007
title: Ścieżki, dopasowania i mierniki
status: todo
owner: null
branch: null
depends_on: [T006]
capabilities: [python]
acceptance:
  - id: AC-1
    run: "cd app && RADAR_LLM=demo python -m pytest -q tests/test_pathways.py tests/test_matching.py tests/test_metrics.py"
  - id: AC-2
    run: "RADAR_LLM=demo python scripts/run_use_case.py uc1 --until pathway"
    expect: "pathway: transfer"
  - id: AC-3
    run: "RADAR_LLM=demo python scripts/run_use_case.py uc2 --until pathway"
    expect: "pathway: akceleracja"
protected:
  - app/tests/test_pathways.py
---
## Objective
Steps d) and e): from card + assessment, recommend a pathway with reasons and the next step, list matched
recipients with explanations, and compute the expected success metrics and the radar-wide counters.

## Context
- Pathway table: `.house/PLAN.md` §3.3. Implement as readable rules in
  `app/radar/pathways/rules.yaml` + `engine.py`; output top pathway, runner-up, the weighted score per
  pathway, the 2–3 criteria that decided it, the next step, and `explain()` that prints the rule.
- Matching (`matching.py`): recipients and needs from T002; score = need similarity (T005) + type/region
  fit + pathway fit; each match carries a one-line reason. Contacts are shown only if consent is stored.
- Metrics (`metrics.py`): per-innovation expected 90-day KPIs per pathway (template in rules.yaml) and
  radar counters (detected, submitted, assessed, with pathway, matches, duplicates flagged, median time
  to first match) from the store. PLAN §3.4.
- Expected outcomes for UC1/UC2: `.house/demo-flow.md`.

## Out of scope
Sending any message to anyone. UI.
