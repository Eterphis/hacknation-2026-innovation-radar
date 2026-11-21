---
id: T020
title: "Signal v1 i rola źródła po etapie normalize"
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
    run: "cd app && .venv/Scripts/python -m pytest -q tests/test_signal_contract.py"
    timeout: 600
  - id: AC-3
    manual: "każde z 4 źródeł golden path (RAD-on, Biblioteka Nauki, EPO, Kohesio) daje Signal zgodny ze schematem na prawdziwej próbce"
protected:
  - app/tests/test_pipeline.py
---
## Objective
Każdy rekord po `normalize` ma obok `Record` dokument `Signal` v1 (schemat z `.house/reports/sources-and-idea-flow.md` §3) zapisany jako JSON. `SourceSpec` ma pole `role` (idea | evidence | reference | demand), `sources.yaml` ustawia je dla wszystkich źródeł, a po normalize jest rozgałęzienie po roli (idea → resolve_org/dedup/gate, evidence → link, reference → rejestr, demand → indeks popytu). Dalsze etapy czytają wyłącznie Signal.

## Context
D-009, D-010; `app/radar/sources/base.py` (SourceSpec), `app/radar/models.py` (Record), `app/radar/pipeline/normalize.py` (apply_mapping), `app/sources.yaml`. Konektory zwracają `Envelope`, mapowanie jest deklaratywne. Exchange zostaje `radar` direct z kluczem = nazwa etapu (ustalenie z sesją architektury).

## Out of scope
Nie przepisywać konektorów ani topologii kolejek. Nie zmieniać kluczy idempotencji.
