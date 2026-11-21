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

## Karta innowacji (ekstrakcja → dojrzałość → ocena → odbiorcy)

```bash
python -X utf8 -m radar.card --in data/normalized/ncbr.jsonl --out data/cards            # wszystkie rekordy ok
python -X utf8 -m radar.card --ids innowacyjny-czujnik-odksztalcen-na-bazie-specjalnych-swiatlowodow-mikrostrukturalnych
```

Dla każdego rekordu powstaje karta `radar.card/v1` (`data/cards/cards.jsonl`) i uzasadnienie dla urzędnika w układzie decyzji (`data/cards/<card_id>.md`): 1. co ustalono (z cytatami i linkami), 2. kryteria, 3. ocena, 4. co przemawia przeciw, 5. ścieżka, odbiorcy i mierniki, 6. ograniczenia.

- **Ekstrakcja** ([`radar/extract.py`](radar/extract.py), [`radar/llm.py`](radar/llm.py)): pola karty (rozwiązanie, problem, co nowego, wymagania, typ, odbiorcy, sygnały dojrzałości, dziedziny), każde z cytatem. Kod sprawdza, czy cytat występuje w źródle; przy błędzie ponawia z listą błędów (maks. 2 razy), potem usuwa niepotwierdzone twierdzenia i oznacza kartę.
- **Dostawca LLM** (`--llm` lub `RADAR_LLM`): `auto` (domyślnie: Claude, gdy jest pakiet `anthropic` i poświadczenia, inaczej reguły), `claude`, `offline`. Claude: `claude-opus-5-5`, structured outputs zgodne ze schematem, włączony serwerowy fallback przy odmowie (`fallbacks: "default"`). Reguły offline są zawsze ostatnim zapasem, więc demo działa bez klucza. Instalacja: `pip install anthropic`.
- **Dojrzałość, ocena, ścieżka** ([`radar/assess.py`](radar/assess.py)): tylko reguły, bez LLM. Pięć kryteriów (dojrzałość, przenaszalność, skala problemu, koszt i wymagania wdrożenia, siła dowodów), każde z uzasadnieniem; brak danych o koszcie to luka, nie ocena. Światła: ≥ 3,8 zielone, ≥ 2,8 żółte.

## GUI operatora (kolejka kart)

```bash
python -X utf8 -m radar.gui              # http://127.0.0.1:8765
python -X utf8 -m radar.gui --rebuild    # najpierw przebuduj karty z data/normalized (offline)
```

- Zakładki Do decyzji / Zatwierdzone / Odrzucone / Wszystkie; lista z oceną, wyszukiwarka, filtr oceny i „ukryte innowacje” (pozostałe filtry pod „Więcej filtrów”).
- Karta: rekomendacja i blok „W skrócie” (co to jest, dla kogo, co dalej, dojrzałość); dowody, kryteria, ryzyka i szczegóły w zwijanych sekcjach; pobranie uzasadnienia jako `.md`.
- Decyzja **Zatwierdź / Odrzuć / Cofnij** z notatką; zapis w `data/decisions.jsonl` (log tylko dopisywany, ostatni wpis wygrywa). Strzałki ↑/↓ przechodzą między kartami.
- Serwer tylko na `127.0.0.1`, biblioteka standardowa Pythona; brak kart → buduje je sam z `data/normalized/ncbr.jsonl`.
