---
id: T002
title: Dane demonstracyjne i korpus porównawczy
status: todo
owner: null
branch: null
depends_on: [T001]
capabilities: [python, research]
acceptance:
  - id: AC-1
    run: "python scripts/validate_seed.py"
    expect: "seed OK"
  - id: AC-2
    run: "python scripts/validate_seed.py --use-cases"
    expect: "use cases OK"
  - id: AC-3
    manual: "Każde źródło korpusu ma w docs/DANE_I_OGRANICZENIA.md wiersz: nazwa, URL, data pobrania, warunki użycia, jak pobrano (API / pobranie ręczne / zapisana strona)."
protected:
  - scripts/validate_seed.py
---
## Objective
`data/seed/` holds everything the demo needs, validated against the T001 contract, so the radar is never
empty and both use cases from `.house/demo-flow.md` run end to end.

## Context
- Read `.house/demo-flow.md` section „Dane, których demo potrzebuje”: exact counts and the planted
  matches (8 gminas with the street-lighting need, 3 schools with the air-quality need, corpus items similar
  to UC1 and UC2).
- Files: `data/seed/innovations.json` (≥ 24 cards, all 5 innovation types, all 4 institution types, mostly
  Podkarpackie), `data/seed/recipients.json` (≥ 20 companies, investors, gminas, schools, grant programmes,
  PCI programmes), `data/seed/needs.json`, `data/corpus/*.jsonl` (≥ 200 records: patents, publications,
  EU/NCBR projects), `data/seed/use_cases/uc1.html`, `uc2.txt`, `data/fixtures/pages/*.html` (6 pages for
  the scan, 2 of them not innovations).
- Corpus sources suggested by the task: e-Wyszukiwarka UPRP, EPO Register, PBN, PPM, dLibra PAN, BazTOL,
  interreg.gov.pl/lista-projektow, NCBR „wyszukiwarka sukcesów beneficjentów”. Prefer bulk/public exports
  or small manual snapshots over scraping; check robots.txt and terms first; record each in
  `docs/DANE_I_OGRANICZENIA.md`. If a source cannot be used in 45 minutes, snapshot by hand and move on.
- Write `scripts/build_corpus.py` so the snapshot is reproducible (reads raw exports in `data/raw/`).
- Fictional records: `example: true`, institution names clearly invented („Gmina Przykładowo”). Never
  attribute invented results to a real institution or person. No personal data of real people.
- `scripts/validate_seed.py` loads every file through the Pydantic models, checks counts, coverage of
  enums, `source_url` + `retrieved_at` on each corpus record, and prints `seed OK`; with `--use-cases`
  it checks the planted matches and prints `use cases OK`.

## Out of scope
Search, scoring, LLM. Live connectors (T004 does detection on fixtures).
