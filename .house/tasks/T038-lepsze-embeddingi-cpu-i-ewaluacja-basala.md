---
id: T038
title: "Embeddingi fastembed (e5-small, CPU) w obrazie i ewaluacja Basala"
status: todo
owner: null
branch: null
depends_on: [T021]
capabilities: []
acceptance:
  - id: AC-1
    run: "cd app && .venv/Scripts/python -m pytest -q"
    timeout: 600
  - id: AC-3
    manual: "na 60 ręcznie oznaczonych rekordach: trafność sektora i decyzji Basala dla hashing vs fastembed zapisana w .house/experiments.csv"
protected:
  - app/tests/test_pipeline.py
---
## Objective
Wariant obrazu z `pip install .[embed]` i modelem `intfloat/multilingual-e5-small` pobranym przy budowie (bez pobierania w runtime), `RADAR_EMBEDDER=fastembed` w Helm, progi `SIMILAR_MIN`/nowości skalibrowane dla tego embeddera; porównanie z domyślnym hashingiem na zbiorze testowym.

## Context
`app/radar/basal/embed.py`, `app/radar/basal/graph.py` (progi skalibrowane dla hashingu: mediana pary 0,08, p95 0,24), `app/radar/basal/classifier.py` (prototypy etykiet).

## Out of scope
GPU, modele > 500 MB.
