---
id: T021
title: "Etap gate (Basal) przed extract: odsiew, typy, priorytet, bez LLM"
status: todo
owner: null
branch: null
depends_on: [T020]
capabilities: []
acceptance:
  - id: AC-1
    run: "cd app && .venv/Scripts/python -m pytest -q"
    timeout: 600
  - id: AC-2
    run: "cd app && .venv/Scripts/python -m pytest -q tests/test_gate.py"
    timeout: 600
  - id: AC-3
    manual: "na danych demo: artykuł historyczny odrzucony z powodem, zgłoszenie z e-mailem zamaskowane, reszta ma institution_type i innovation_type z pewnością"
protected:
  - app/tests/test_pipeline.py
---
## Objective
Nowy etap Celery `gate` per rekord, po `dedup` i przed `extract`, bez LLM: odsiew (spam, treść obraźliwa, za mało treści, prywatna firma bez instytucji publicznej, duplikat, dane osobowe → maskowanie albo hold) z zapisanym powodem; etykiety institution_type (szkoła | uczelnia | instytut | JST | inna_publiczna | unknown) i innovation_type (technologiczna | organizacyjna | edukacyjna | społeczna | procesowa | usługowa | unknown) z pewnością i źródłem; maturity_hint; priorytet. Kolejka `extract` (i dalsze LLM) z `x-max-priority`, priorytet ustawia gate; `unknown` → niski priorytet albo hold. Obecny PREFILTER z `extract` przenieść tutaj.

## Context
`sources-and-idea-flow.md` §5, D-005 (nic nie ginie, liczniki), `app/radar/pipeline/celery_app.py` (kolejki, DLX), `app/radar/pipeline/tasks.py` (PREFILTER, extract), `app/radar/pipeline/extract.py::INNOVATION_TYPES` (wspólna lista, dopisać `unknown`).

## Out of scope
Bez LLM i bez klasyfikatora ML (lokalny klasyfikator to osobny krok wieczorem). IdeaTask na klaster to T022.

## Stan (2026-11-21, sesja app/Helm)
Zrobione w `app/radar/basal/` + etap `gate` w `pipeline/tasks.py`: odsiew z powodami, PII maskowane, 7 osi (sektor PKD, obszar technologii, typ innowacji, typ instytucji, dojrzałość, koszt, województwo), priorytet → RabbitMQ `x-max-priority` na kolejkach link/extract/maturity/score, uczona głowa decyzji (`/api/basal/train`, zapis w tabeli `settings`). Zostało: klasyfikator ML na embeddingach (fastembed) i kalibracja progów na zbiorze testowym.
