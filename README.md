# hacknation-2026-innovation-radar

HackNation 2026 (Bydgoszcz, 21–22.11.2026): **Radar Innowacji**, the task from Podkarpackie Centrum Innowacji.

Shared contest state lives in [`.house/`](.house/): spec, tasks, decisions, questions, progress.

## Szybki start w Dockerze

Wymagany Docker Desktop (Windows / macOS) albo Docker Engine z Compose v2 (Linux). Docker musi być uruchomiony: `docker info` nie może zwracać błędu.

```bash
git clone https://github.com/Eterphis/hacknation-2026-innovation-radar.git
cd hacknation-2026-innovation-radar
docker compose up -d --build
```

- Przeglądarka danych: **http://localhost:8765**.
- Kontener `scheduler` od razu pobiera dane z Interreg i NCBR (pierwszy raz około 5 minut), a potem odświeża je co 24 h. Po pobraniu wystarczy odświeżyć stronę.
- Dane (surowe pliki, JSONL i baza `radar.db`) trafiają do `./data` na Twoim komputerze i nie giną po zatrzymaniu kontenerów.

```bash
docker compose logs -f scheduler            # postęp pobierania
docker compose run --rm gui refresh         # odśwież teraz, bez czekania na harmonogram
docker compose run --rm gui store stats     # co jest w bazie
docker compose down                         # zatrzymaj (dane zostają w ./data)
```

Ustawienia (port, częstotliwość odświeżania, klucz Claude dla kart) są w pliku `.env`: skopiuj `.env.example` do `.env` i zmień, co trzeba. Wszystkie polecenia i rozwiązywanie problemów opisuje [`docs/docker.md`](docs/docker.md).

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

**Interreg 2021–2027 – wykaz projektów** ([`radar/sources/interreg.py`](radar/sources/interreg.py)):

```bash
python -X utf8 -m radar.sources.interreg --out data/normalized/interreg.jsonl --csv data/normalized/interreg.csv
python -X utf8 -m radar.sources.interreg --offline   # z zapisanego pliku, bez sieci
```

- Pobiera stronę `interreg.gov.pl/lista-projektow/`, odczytuje z niej aktualny link do pliku XLSX (nazwa zawiera datę publikacji), pobiera plik i zapisuje oba do `data/raw/interreg/`. XLSX czytany biblioteką standardową ([`radar/xlsx.py`](radar/xlsx.py)).
- Kolumny rozpoznawane po nagłówkach, nie po pozycji; brak wymaganej kolumny przerywa pobieranie z komunikatem (zmiana formatu pliku), brak pozostałych jest wypisywany w podsumowaniu.
- Jeden wiersz = jeden rekord `radar.record/v1`: tytuł, opis, partner wiodący z lokalizacją (kod, miejscowość, gmina, powiat, region, kraj), partnerzy, program, numer projektu, fundusz, cel szczegółowy, zakres interwencji, wartość w EUR, stopa i wyliczone dofinansowanie, okres ze statusem, województwo (dla partnerów z Polski), w `provenance` adres pliku i numer wiersza.
- Źródło nie ma strony per projekt, więc `url` jest pusty; opisy dłuższe niż 4000 znaków są w pliku ucięte (ostrzeżenie `description_truncated_in_source`).

**Odświeżenie obu źródeł jednym poleceniem** ([`radar/refresh.py`](radar/refresh.py), pełna instrukcja: [`docs/odswiezanie-danych.md`](docs/odswiezanie-danych.md)):

```bash
python -X utf8 -m radar.refresh              # Interreg + NCBR, pobiera tylko to, co nowe
python -X utf8 -m radar.refresh --dry-run    # pokaż, co by zrobił
python -X utf8 -m radar.refresh --force      # wszystko od nowa
python -X utf8 -m radar.gui                  # przeglądarka danych z bazy: http://127.0.0.1:8765
```

- Interreg: XLSX pobierany tylko, gdy link na stronie wskazuje inny plik albo zapisany jest uszkodzony (SHA-256); pobrany plik musi być poprawnym XLSX.
- NCBR: lista pobierana ponownie po `--max-age` godzinach (domyślnie 24), strony szczegółów już na dysku nie są pobierane drugi raz.
- Przebudowa pomijana, gdy wejście się nie zmieniło; poprzedni wynik zostaje w `*.prev.jsonl`, spadek liczby rekordów o ponad połowę daje ostrzeżenie i kod 1.
- Blokada `data/.refresh.lock` przed równoległym uruchomieniem (także między kontenerami), błąd jednego źródła nie zatrzymuje drugiego.

**Baza danych** ([`radar/store.py`](radar/store.py), SQLite z biblioteki standardowej, plik `data/radar.db`): po każdym odświeżeniu rekordy są zapisywane z historią (pierwsze pojawienie się, zmiany opisu, usunięcie ze źródła). Baza ma wyszukiwanie pełnotekstowe działające też bez polskich znaków, organizacje wspólne dla źródeł, karty i przebiegi odświeżania (`refresh_runs`). Da się ją w całości odtworzyć z `data/raw/` (`radar.refresh --offline`).

```bash
python -X utf8 -m radar.store stats
python -X utf8 -m radar.store search "pompa ciepla"
python -X utf8 -m radar.store export --source ncbr_sukcesy --out eksport.jsonl
python -X utf8 -m radar.card --stale         # karty tylko dla nowych i zmienionych rekordów
```

**Docker** ([`docs/docker.md`](docs/docker.md)): `docker compose up -d --build` uruchamia przeglądarkę na http://localhost:8765 i harmonogram odświeżania co 24 h; dane trafiają do `./data`.

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

## GUI: podgląd wczytanych danych

```bash
python -X utf8 -m radar.gui                    # wszystkie data/normalized/*.jsonl, http://127.0.0.1:8765
python -X utf8 -m radar.gui --data data/normalized/interreg.jsonl
```

- Pokazuje wyłącznie to, co konektory zapisały w plikach JSONL: listę rekordów ze wszystkich źródeł (wyszukiwarka, filtr źródła, jakości i województwa) i każdy rekord bez zmian.
- **Źródło wczytania** przy każdym rekordzie: nazwa źródła, strona projektu albo plik źródłowy z numerem wiersza, strona listy, czasy pobrania, wersja konektora, schemat, ID rekordu, hash treści, plik danych i ścieżki do zapisanych surowych stron lub pliku.
- Dane rekordu z wartością odczytaną obok wartości ze źródła (kwoty, okres, województwo), treść według sekcji, jakość wczytania (powody `needs_review`) i surowy JSON rekordu.
- Tylko odczyt; serwer na `127.0.0.1`, biblioteka standardowa Pythona.
