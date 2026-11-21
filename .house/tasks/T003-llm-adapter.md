---
id: T003
title: Adapter LLM z trybem demo
status: todo
owner: null
branch: null
depends_on: [T001]
capabilities: [python, claude-api]
review: always
acceptance:
  - id: AC-1
    run: "cd app && RADAR_LLM=demo python -m pytest -q tests/test_llm.py"
  - id: AC-2
    run: "env -u ANTHROPIC_API_KEY RADAR_LLM=anthropic python scripts/keycheck.py"
    expect: "mode: demo"
  - id: AC-3
    run: "cd app && python -m pytest -q tests/test_llm_replay.py"
protected:
  - app/tests/test_llm_replay.py
---
## Objective
One module, `app/radar/llm.py`, that every AI feature calls. It returns validated Pydantic objects, has a
timeout and a visible error, and works without any key by replaying recorded responses.

## Context
- Interface: `complete_structured(task: str, prompt: str, schema: type[BaseModel], *, effort: str) -> T`
  and `record` / `replay` keyed by `sha256(task + prompt + model)`; recordings in `data/recorded_llm/`.
- Backends, chosen by `RADAR_LLM`:
  - `anthropic`: official `anthropic` Python SDK, model from `RADAR_MODEL` (default `claude-opus-5-5`),
    structured outputs via `client.messages.parse(..., output_format=Schema)` (check the SDK README for
    the exact helper), adaptive thinking, `output_config.effort` set explicitly (`low` for extraction and
    classification, `medium` for assessment), server-side refusal fallback
    (`betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"`), check `stop_reason` before
    reading content, typed SDK exceptions (rate limit vs. bad request), timeout 60 s.
  - `demo`: replay only; a missing recording raises a clear `DemoRecordingMissing` that the API turns into
    a labelled message, never a crash.
  - `RADAR_LLM=anthropic` with no credentials falls back to `demo` and says so (`mode: demo`).
- Before writing SDK code read the claude-api skill (`/claude-api`, Python README); do not guess method
  names. Never put the key in code, logs, or recordings.
- `scripts/keycheck.py`: one cheap real call when a key is present, prints `mode: anthropic ok` or
  `mode: demo (reason)`, exits 0 in both cases, non-zero only on a broken key.
- Prompts live in `app/radar/prompts/*.md` (Polish domain text, English instructions are fine) so they are
  reviewable; every prompt asks for source quotes and allows "brak danych".

## Out of scope
The actual extraction/assessment prompts' quality (T004, T006 own them). UI.
