---
id: T004
title: Zgłoszenie i automatyczne wykrywanie
status: todo
owner: null
branch: null
depends_on: [T002, T003]
capabilities: [python, claude-api]
acceptance:
  - id: AC-1
    run: "cd app && RADAR_LLM=demo python -m pytest -q tests/test_intake.py"
  - id: AC-2
    run: "cd app && RADAR_LLM=demo python -m pytest -q tests/test_detect.py"
  - id: AC-3
    run: "RADAR_LLM=demo python scripts/run_use_case.py uc2 --until card"
    expect: "card: .*szkola"
protected:
  - app/tests/test_intake.py
  - app/tests/test_detect.py
---
## Objective
Steps a) and b) of the demo: free text from the form becomes an `InnovationCard` with provenance on every
AI field, and the scanner turns public pages into ranked `Candidate`s, rejecting pages that are not
innovations.

## Context
- `app/radar/ingest/extract.py`: text (+ optional URL) → card via `llm.complete_structured`
  (effort `low`). Each filled field quotes the span it came from; unknown fields stay empty and are listed
  as `missing_fields` for the UI to ask about. Consent flag from the form is stored; without consent the
  creators' contact is not stored.
- `app/radar/ingest/detect.py`: source connectors behind one interface (`fetch() -> list[RawDoc]`); for the
  demo a `FixtureSource` reading `data/fixtures/pages/` and `data/seed/use_cases/uc1.html`, plus one real
  connector (RSS/HTML list page) if time allows, rate-limited and honouring robots.txt. Classifier
  (LLM, effort `low`) returns `is_innovation`, type, confidence, reason; threshold in config.
- Record demo responses for UC1, UC2 and every fixture page into `data/recorded_llm/` (T003 record mode),
  so tests and the demo run without a key.
- `scripts/run_use_case.py <uc> --until card|assessment|pathway` prints a short summary; later tasks extend it.

## Out of scope
Scoring, similarity, UI.
