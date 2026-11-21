---
id: T012
title: Dokumentacja dla jury i wdrożenia
status: todo
owner: null
branch: null
depends_on: [T008]
capabilities: [writing]
acceptance:
  - id: AC-1
    run: "python scripts/check_docs.py"
    expect: "docs OK"
  - id: AC-2
    manual: "Czysty klon na innej maszynie z samym Dockerem: `docker compose up --build` z README uruchamia aplikację w trybie demo w < 10 min bez pytań."
protected:
  - scripts/check_docs.py
---
## Objective
Documents that answer, in Polish, everything the task says the jury will look for (sections 5 and 9 of the
task text), and that the winning team would hand over with the code (§3 ust. 5 regulaminu: complete source
+ documentation).

## Context
Files and required headings (`scripts/check_docs.py` checks they exist and are non-empty):
- `README.md`: Co to jest · Jak uruchomić (pierwsza komenda w README to `docker compose up --build`; potem z
  kluczem i bez, testy przez `docker compose run --rm app test`, tryb deweloperski) · Demo (URL, film) · Architektura (obraz) ·
  Licencja EUPL-1.2 · Autorzy.
- `docs/ARCHITEKTURA.md`: komponenty, przepływ a→e, kontrakt, API (`/docs`).
- `docs/OCENA_I_REKOMENDACJE.md`: rubryka renderowana z `rubric.yaml`, reguły ścieżek z `rules.yaml`,
  jak działa nadpisanie przez człowieka. (Przejrzystość kryteriów.)
- `docs/DANE_I_OGRANICZENIA.md`: źródła danych (tabela z T002), założenia AI, ograniczenia (halucynacje,
  język, pokrycie źródeł, dane przykładowe), czego system nie robi.
- `docs/BEZPIECZENSTWO_I_RODO.md`: dane osobowe twórców, zgody, minimalizacja, role, przechowywanie,
  klucze, co trzeba dodać przed produkcją (auth, audyt).
- `docs/WDROZENIE.md`: skalowanie na wiele organizacji (org_id, operator regionalny), integracje (API,
  CSV, możliwe: BIP, USOS, systemy JST, bazy UPRP/EPO), koszt LLM na innowację, plan rozwoju po
  hackathonie (30/90/180 dni).

## Out of scope
Pitch materials (T014).
