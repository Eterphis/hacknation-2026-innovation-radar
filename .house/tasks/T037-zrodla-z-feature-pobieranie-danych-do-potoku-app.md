---
id: T037
title: "Źródła z feature/pobieranie-danych (NCBR, Interreg, crawler) jako źródła potoku app/"
status: todo
owner: null
branch: null
depends_on: []
capabilities: []
acceptance:
  - id: AC-1
    run: "cd app && .venv/Scripts/python -m pytest -q"
    timeout: 600
  - id: AC-3
    manual: "rekordy NCBR i Interreg przechodzą Basala i agenta, pojawiają się na stronie Przegląd i w grafie"
protected:
  - app/tests/test_pipeline.py
---
## Objective
Gałąź `feature/pobieranie-danych` ma osobny pakiet `radar/` (katalog główny) z konektorami NCBR, Interreg, crawlerem stron i bazą SQLite. Podłączyć jego wynik (`radar.record/v1`, JSONL w `data/normalized/`) do potoku `app/` jako źródła `snapshot` w `app/sources.yaml` z mapowaniem pól, bez przepisywania konektorów; docelowo konektory jako typy w `app/radar/sources/registry.py`.

## Context
`app/sources.yaml` (typ `snapshot`, mapping JMESPath), `.house/reports/main-flow.md`, todo.md na gałęzi `feature/pobieranie-danych`. Dwie bazy kodu: uzgodnić z właścicielem tamtej gałęzi, która wersja zostaje.

## Out of scope
Zmiany w samych konektorach tamtej gałęzi.
