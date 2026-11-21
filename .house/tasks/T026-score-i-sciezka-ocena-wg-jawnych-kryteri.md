---
id: T026
title: "score i ścieżka: ocena wg jawnych kryteriów, rekomendacja, odbiorcy"
status: todo
owner: null
branch: null
depends_on: [T024, T027]
capabilities: []
acceptance:
  - id: AC-1
    run: "cd app && .venv/Scripts/python -m pytest -q"
    timeout: 600
  - id: AC-2
    run: "cd app && .venv/Scripts/python -m pytest -q tests/test_score.py"
    timeout: 600
  - id: AC-3
    manual: "dwa przypadki demo (uczelnia, gmina) mają ocenę 0-5 na każde kryterium z uzasadnieniem i co najmniej 1 odbiorcę z uzasadnieniem"
protected:
  - app/tests/test_pipeline.py
---
## Objective
Etap `score`: ocena 0–5 na kryteria (dojrzałość, przenaszalność, skala problemu, koszt wdrożenia, siła dowodów, innowacyjność) z uzasadnieniem; rekomendowana ścieżka (rozwój / transfer / komercjalizacja / wdrożenie w innej organizacji / grant); 1–3 odbiorców (beneficjenci Kohesio, gminy o podobnych cechach z GUS BDL) i mierniki skuteczności (treść zadania §6e).

## Context
Stub `score` i `build_reasoning` w `app/radar/pipeline/tasks.py`, `sources-and-idea-flow.md` §7-8.

## Out of scope
Wysyłka do odbiorców (D-008 pkt 5).

## Stan (2026-11-21, sesja app/Helm)
Częściowo: `app/radar/pipeline/assess.py` liczy 6 kryteriów z wagami, ścieżki z „kto co robi”, ryzyka z mitygacjami, odbiorców (typy + instytucje z danych), mierniki skuteczności; `reassess` codziennie z beat. Zostało: odbiorcy z rejestrów (Kohesio beneficjenci, GUS BDL), kalibracja wag z PCI.
