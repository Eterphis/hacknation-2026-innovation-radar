---
id: T005
title: Wyszukiwanie podobnych i dublowania
status: todo
owner: null
branch: null
depends_on: [T002]
capabilities: [python]
acceptance:
  - id: AC-1
    run: "cd app && python -m pytest -q tests/test_similarity.py"
  - id: AC-2
    run: "python scripts/run_use_case.py uc1 --until similar"
    expect: "similar: 3"
protected:
  - app/tests/test_similarity.py
---
## Objective
For any card, return the top-k similar items from the corpus and from other cards, with a score, the
reason (matched terms) and the source link, and flag likely duplicates. Deterministic, offline, under 2 s.

## Context
- `app/radar/similarity.py`: BM25 (`rank-bm25`) over title + problem + solution + keywords, Polish-aware
  normalisation (lowercase, diacritics folded for matching only, simple stemming or prefix trimming,
  stop-word list in `data/stopwords_pl.txt`). Optional embeddings behind a flag; BM25 must work alone.
- Separate result groups: `corpus` (patents, publications, projects) and `radar` (other cards = possible
  duplicate work or a ready solution elsewhere). Duplicate flag above a tuned threshold.
- Tests use the planted pairs from T002 (UC1 and UC2 must find their planted neighbours in the top 3) and
  one negative pair.
- Output feeds the `nowosc` criterion in T006 and the "ten problem ma już N instytucji" view.

## Out of scope
Scoring, UI, live patent APIs.
