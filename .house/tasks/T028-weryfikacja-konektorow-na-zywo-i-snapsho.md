---
id: T028
title: "Weryfikacja konektorów na żywo i snapshoty prawdziwych próbek"
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
    manual: "openaire-projekty-pl, radon-projekty, kohesio-projekty, epo-patenty-prz: jedno prawdziwe pobranie z poprawnym mapowaniem; wynik w .house/reports/data-access.md"
protected:
  - app/tests/test_pipeline.py
---
## Objective
Konfiguracje w `app/sources.yaml` oznaczone [sprawdzić] są potwierdzone prawdziwym zapytaniem (parametry, stronicowanie, record_path, mapping) i włączone tam, gdzie działają; z każdego źródła mała próbka w `app/samples/` z atrybucją źródła i licencji do testów kontraktu.

## Context
`.house/reports/data-access.md`, `app/sources.yaml`. Biblioteka Nauki OAI-PMH sprawdzona 2026-11-21: 20 rekordów na stronę, resumptionToken, DOI w dc:identifier, mapowanie działa.

## Out of scope
Konta i klucze zakłada człowiek (Q-005).
