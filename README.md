# hacknation-2026-innovation-radar

HackNation 2026 (Bydgoszcz, 21–22.11.2026): **Radar Innowacji**, the task from Podkarpackie Centrum Innowacji.

Shared contest state lives in [`.house/`](.house/): spec, tasks, decisions, questions, progress.

## Setup

This repo is a contest of the AI Software House toolkit, which is vendored in our main repo
([Eterphis/hacknation-2026-odwolania2json](https://github.com/Eterphis/hacknation-2026-odwolania2json)).
Follow that repo's `TEAM.md` first, then fetch this repo into it:

```bash
cd hacknation-2026-odwolania2json
python3 house/bin/house sync                      # clones this repo into house/contests/radar-innowacji
python3 house/bin/house adapt radar-innowacji     # your agents, skills and hooks (per machine, gitignored)
cd house/contests/radar-innowacji && claude       # then /house-start with the full task text
```

On Windows use `py -3.12 house\bin\house …` instead of `python3 house/bin/house …`.

## Pobieranie danych

Konektory źródeł są w [`radar/sources/`](radar/sources/). Używają tylko biblioteki standardowej Pythona (≥ 3.11), więc niczego nie trzeba instalować.

**NCBR – wyszukiwarka sukcesów beneficjentów** ([`radar/sources/ncbr.py`](radar/sources/ncbr.py)):

```bash
python -X utf8 -m radar.sources.ncbr --out data/normalized/ncbr.jsonl --csv data/normalized/ncbr.csv
python -X utf8 -m radar.sources.ncbr --offline   # przebudowa z zapisanych stron, bez sieci (tryb demo)
```

- Pobiera listę kart i stronę szczegółów każdego projektu (domyślnie 1 s przerwy między zapytaniami). Surowe strony trafiają do `data/raw/ncbr/` i przy kolejnym uruchomieniu są brane z dysku (`--refresh` wymusza ponowne pobranie).
- Wynik to rekordy `radar.record/v1` w JSONL: tytuł, sekcje opisu (`problem`, `result`, `users`, `challenges`, `advice`), `text_for_llm`, organizacje i osoby, finansowanie, okres ze statusem, województwo, słowa kluczowe, `content_hash`, `quality` (`ok` / `needs_review` z powodami) i `provenance`.
- Karta nie ginie: błąd pobrania albo brak opisu oznacza `needs_review` z powodem, a nie pominięcie rekordu.
- `data/` jest w `.gitignore` (licencja treści źródła do potwierdzenia).

Testy: `python -X utf8 -m unittest discover -s tests -t .`
