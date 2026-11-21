---
id: T014
title: "Zgłoszenie: PDF, film, opis, pitch"
status: todo
owner: null
branch: null
depends_on: [T011]
capabilities: [writing, video]
acceptance:
  - id: AC-1
    run: "python scripts/check_submission.py"
    expect: "submission OK"
  - id: AC-2
    manual: "Film ≤ 180 s, publiczny link otwiera się w incognito po przetworzeniu; pokazuje działający produkt (nie makiety)."
  - id: AC-3
    manual: "Pitch 5 min przećwiczony 3 razy na czas; odpowiedzi na 5 najbardziej prawdopodobnych pytań jury w pitch/QA.md."
protected:
  - scripts/check_submission.py
---
## Objective
Everything the formal requirements list (task text §4) is ready by 10:30, and the 5-minute stage II pitch
is rehearsed.

## Context
- `pitch/SUBMISSION.md` (pasted into Hacktribe): tytuł · opis problemu i rozwiązania · sposób działania i
  główne funkcje · link do filmu · link do repo · link do demo · źródła danych, założenia i ograniczenia
  (skrót z docs) · licencja.
- `pitch/slides.pdf` ≤ 10 slides: 1 problem (historia jednej osoby) · 2 dlaczego dziś to nie działa ·
  3 rozwiązanie w jednym zdaniu · 4–6 demo a→e (zrzuty z T011) · 7 jak oceniamy (rubryka, przejrzystość) ·
  8 co dzieje się dalej z innowacją (ścieżki + mierniki) · 9 wdrożenie i skala (wiele instytucji, API,
  EUPL, RODO) · 10 prośba / następny krok z PCI.
- `pitch/video.url`: film ≤ 3 min, long-demo template in `.house/protocols/demo-video.md`; recorded from
  the real app; captions readable without sound; uploaded early, visibility checked.
- `pitch/FACTS.md`: every number used on slides or in the film, with source. Example data says „Przykład”.
- `pitch/PITCH.md`: 5-minute script for stage II (criteria: spójność, jasność, zainteresowanie,
  pomysłowość prezentacji, charyzma) + `pitch/QA.md`.
- `scripts/check_submission.py`: slides ≤ 10 pages (pypdf), all SUBMISSION.md sections present,
  `video.url` and `.house/demo-url.txt` non-empty, prints `submission OK`.

## Out of scope
New features after 09:30.
