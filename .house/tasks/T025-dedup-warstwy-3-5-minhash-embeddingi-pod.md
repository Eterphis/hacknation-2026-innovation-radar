---
id: T025
title: "dedup warstwy 3-5: MinHash, embeddingi, podobne rozwiązania"
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
    run: "cd app && .venv/Scripts/python -m pytest -q tests/test_dedup.py"
    timeout: 600
  - id: AC-4
    manual: "na docker compose (współbieżne workery) karta kompozytów powstaje z demo:pub:1 i ma tech_ready"
  - id: AC-3
    manual: "zbiór 40 par (20 duplikatów, 20 nie): precyzja >= 0.9, wynik w .house/experiments.csv"
protected:
  - app/tests/test_pipeline.py
---
## Objective
Dedup z blokowaniem (org_id / rok±1 / klasa), Jaccard tytułów, MinHash abstraktów, embeddingi wielojęzyczne z progami 0.95/0.85, tabela par z decyzją (duplicate | related | similar | distinct | needs_review) i powodem po polsku; po ekstrakcji lista „podobne rozwiązania” z flagą „możliwe dublowanie prac”; narzędzie `find_duplicates(record_id)`.

## Context
`pipeline-design.md` §16, D-007; obecny dedup (DOI, tytuł+rok) w `app/radar/pipeline/tasks.py::dedup`.

Znany błąd do naprawy w tym zadaniu (wykryty 2026-11-21 na docker compose): przy współbieżnych workerach rekordem kanonicznym zostaje ten, który pierwszy przeszedł `normalize`, a nie najpełniejszy. W demo kanoniczny jest `demo:pub:4` (krótszy opis bez pilotażu), więc karta ma `exploring` zamiast `tech_ready`. Wybór kanonicznego wg §16 (najpełniejszy opis, abstrakt PL, otwarta licencja, DOI, najnowsza wersja) z przepięciem karty.

## Out of scope
Łączenie dowodów różnego typu (T024).

## Stan (2026-11-21, sesja app/Helm)
Częściowo: embeddingi (`hashing-stem6+char4`, opcjonalnie fastembed e5-small) i krawędzie podobieństwa w tabeli `edges`; lista „podobne rozwiązania” na karcie i para „dublowanie prac” w /api/insights. Zostało: warstwy MinHash/pary z decyzją i wybór rekordu kanonicznego (błąd opisany wyżej).
