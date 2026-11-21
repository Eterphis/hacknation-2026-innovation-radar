---
id: T027
title: "Agent analyze + recenzent + brief (I-011, I-014)"
status: todo
owner: null
branch: null
depends_on: [T021]
capabilities: []
acceptance:
  - id: AC-1
    run: "cd app && .venv/Scripts/python -m pytest -q"
    timeout: 600
  - id: AC-2
    run: "cd app && .venv/Scripts/python -m pytest -q tests/test_analyze.py"
    timeout: 600
  - id: AC-3
    manual: "karta w UI ma sekcje: Co ustalono, Kryteria, Ocena, Co przemawia przeciw, Rozstrzygnięcie, Ograniczenia; każde twierdzenie ma cytat albo link do rekordu"
protected:
  - app/tests/test_pipeline.py
---
## Objective
Agent z narzędziami (get_record, lookup_registry, find_similar, find_duplicates, list_recipients) przez router LLM z fallbackiem; Assessment JSON walidowany (cytaty sprawdzane w kodzie), jedno przejście recenzenta „Co przemawia przeciw”, brief jednostronicowy dla urzędnika. Działa też z providerem `mock` w trybie demo.

## Context
`sources-and-idea-flow.md` §7-8, `ideation-3.md`, `app/radar/llm/router.py`, `app/radar/pipeline/extract.py` (wzorzec walidacji cytatów).

## Out of scope
Feed i filmy (D-009, D-010: po golden path).

## Stan (2026-11-21, sesja app/Helm)
Częściowo: agent = narzędzia w kodzie (podobne, kontekst regionu, odbiorcy) → wersja regułowa → opcjonalne doprecyzowanie przez LLM (także lokalny Bielik) → Basal-recheck. Zostało: pętla tool-calling z prawdziwym LLM, recenzent „co przemawia przeciw” jako osobne przejście, walidacja cytatów w Assessment.
