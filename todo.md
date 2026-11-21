# TODO: crawler bez LLM dla wszystkich źródeł z zadania

Plik przekazania pracy dla kolejnej sesji Claude. Przeczytaj go w całości, potem `README.md`, `docs/odswiezanie-danych.md` i `docs/docker.md`. Odpowiadaj użytkownikowi po polsku.

## Cel

Zadanie konkursowe (PDF PCI, §7) wymienia kategorie źródeł i wymaga **cyklicznej aktualizacji** bazy innowacji (nowe rozwiązania, zmiany statusu wdrożenia, aktualność informacji):

- **Nauka i technologie:** Google Scholar, polskie uczelnie i instytuty badawcze, bazy patentowe
- **Projekty badawcze i innowacyjne:** NCBR, PARP, NCN, Fundusze Europejskie, CORDIS
- **Startupy i biznes:** strony firm, startupów, inkubatorów, centrów transferu technologii, instytucji finansujących
- **Administracja i edukacja:** strony samorządów, szkół, uczelni, instytucji publicznych, raporty i opisy zrealizowanych projektów

Do zrobienia: własny **crawler** (w duchu Firecrawl: strona/PDF → czysty tekst + metadane), który zbiera dane ze wszystkich kategorii, **normalizuje je regułami (bez LLM)** do rekordu `radar.record/v1`, zapisuje do bazy SQLite i odświeża każde źródło według jego harmonogramu.

## Ustalone decyzje (nie zmieniać bez pytania użytkownika)

- **Bez LLM** w zbieraniu i normalizacji: struktura HTML, JSON-LD/OpenGraph, słowniki, wyrażenia regularne.
- **Własny crawler na bibliotece standardowej** Pythona ≥ 3.11, jak cały projekt. Jedyna opcjonalna zależność: `pypdf` (BSD, zgodna z EUPL) do tekstu z PDF. Nie Firecrawl: chmura wymaga konta i klucza, self-hosted to Redis + Playwright na AGPL-3.0.
- **Grzecznie i legalnie:** `robots.txt`, limit zapytań na host (domyślnie 1 na 2 s), User-Agent `innovation-radar-harvester/0.1` z `radar/http.py`. **Żadnego obchodzenia zabezpieczeń** (CAPTCHA, Incapsula, wyzwania JS). Zablokowane źródło dostaje status `blocked` i opis w dokumentacji.
- Licencja kodu EUPL-1.2. Dane w `data/` są w `.gitignore`.
- Nigdy nie usuwaj plików ani treści z `.house/` (wolno tylko dopisywać).

## Mapowanie źródeł z zadania

| Źródło | Jak | Stan |
|---|---|---|
| Google Scholar | brak API, regulamin zabrania scrapowania → zamiennik **OpenAlex API** + **Biblioteka Nauki OAI-PMH** | do zrobienia |
| Uczelnie, instytuty | **RAD-on opendata** (instytucje z REGON/NIP/typem, ~49k projektów z abstraktami) + crawler stron CTT/aktualności | do zrobienia |
| Bazy patentowe | **EPO Linked Data + XML publikacji**: gotowy konektor w commicie `5f6f6bf` (lokalny branch `feature/pobieranie-epo`, plik `radar/sources/epo.py`); UPRP blokuje automaty → **import ręcznego eksportu** | do przywrócenia |
| NCBR | `radar/sources/ncbr.py` | jest |
| NCN | projekty z RAD-on | do zrobienia |
| PARP, Fundusze Europejskie | lista projektów FE 2021–2027 (XLSX z dane.gov.pl / funduszeeuropejskie.gov.pl) + Kohesio | do zrobienia, adres do ustalenia |
| CORDIS | otwarte zrzuty Horizon Europe/H2020, filtr organizacji z PL | do zrobienia, adres do ustalenia |
| Interreg | `radar/sources/interreg.py` | jest |
| Startupy, inkubatory, CTT, instytucje finansujące | **crawler stron** z `config/sites.json` | w trakcie |
| Samorządy, szkoły, instytucje publiczne, raporty | **crawler stron** + PDF | w trakcie |
| PBN, PAN dLibra, BazTOL | token / wyzwanie JS / katalog linków → ograniczenie; PAN zastąpiony Biblioteką Nauki | opisać |

Wyniki realnych wywołań każdego źródła: `.house/reports/data-access.md`.

## Postęp (2026-11-21, sesja na `feature/pobieranie-danych`, bez commita)

Zrobione w tym worktree (kroki 1–3 i 6–10):
- `radar/crawl/crawler.py` + `radar/crawl/__main__.py` (dry-run, `sites`), opcja witryny `require_date`;
- poprawki ekstrakcji: klasa boilerplate na `<body>` nie ukrywa już strony; tytuł, gdy `<h1>` to logo serwisu; nazwy organizacji nie sklejają się między akapitami;
- `config/sites.json`: 9 włączonych witryn (nauka 2, biznes 3, projekty 1, administracja 3) sprawdzonych przez dry-run, 7 wyłączonych z opisem blokady;
- rejestr `Source` w `radar/refresh.py`, `--due-only`, `--category`, `--list`, źródło `web`, adapter konektorów z `main(argv)` (rejestruje się sam, gdy moduł istnieje), uzupełnianie kategorii starych rekordów;
- scheduler co `REFRESH_TICK_MINUTES` z `--due-only`, `WITH_PDF`, `config/` w obrazie i jako wolumen (obraz zbudowany lokalnie);
- GUI: filtr i liczniki kategorii, sekcja „Ocena crawlera”, wydawca strony zamiast „beneficjent nieustalony”;
- `docs/zrodla.md`, aktualizacja README, `docs/odswiezanie-danych.md`, `docs/docker.md`, `.env.example`;
- testy: 123 (nowe: `test_crawl_extract`, `test_crawl_classify`, `test_crawl_frontier`, `test_crawler`, rozszerzone `test_store`, `test_refresh`, `test_gui`).

Kroki 4 i 5 (Biblioteka Nauki + OAI, OpenAlex, RAD-on, EPO, CORDIS, FE, UPRP) zrobione w osobnych sesjach i przeniesione tutaj (pliki skopiowane z ich worktree, bez commitów). W rejestrze: Biblioteka Nauki i OpenAlex jako `incremental` (okno czasowe, brakujące rekordy nie są usuwane), UPRP pomijany bez błędu, gdy w `data/import/uprp/` nie ma eksportu. Testy: 207.

Do sprawdzenia: OpenAlex nie przeszedł jeszcze próby online (429, wyczerpany dzienny limit IP; fixture odtworzony ze schematu API). Pełne przebiegi RAD-on (~30 min), EPO i CORDIS uruchomi pierwszy raz scheduler.

## Stan repozytorium (z poprzedniej sesji)

- Branch roboczy: `feature/pobieranie-danych` na `origin` (ostatni commit `199ce19`). W tym worktree branch nazywa się `claude/data-refresh-intereg-ecbr-b185a0` i wskazuje ten sam commit.
- Już działa i jest wypchnięte:
  - `radar/refresh.py`: odświeżanie Interreg + NCBR z pomijaniem już pobranych plików, blokadą (z nazwą hosta), zapisem do bazy;
  - `radar/store.py`: baza `data/radar.db` (SQLite, WAL), rekordy z historią (`record_versions`, `first_seen`, `changed_at`, `removed_at`), FTS5 z `fold()`, organizacje, karty, `refresh_runs`;
  - GUI `radar/gui/` na bazie (`--host`, wyszukiwanie, historia);
  - `radar.card --stale`;
  - Docker: `Dockerfile`, `docker-compose.yml` (`gui` + `scheduler`), `radar/container.py`;
  - 81 testów w `tests/`.

### Niezacommitowane zmiany w tym worktree (do sprawdzenia i dokończenia)

1. **`radar/store.py`**:
   - migracja **v2**: kolumna `records.category` z indeksem, tabele `crawl_sites` i `crawl_pages`;
   - `REMOVAL_GUARD_RATIO = 0.5`: `upsert_source(..., category=None, force_removal=False)` nie oznacza usuniętych, gdy zniknęłaby ponad połowa rekordów źródła (licznik `removal_skipped`);
   - nowa funkcja `mark_removed(conn, source, ids)`;
   - filtr `category` w `list_records`, `category` w `summary_row`, `categories` w `stats`.
   - Sprawdzone: migracja na kopii prawdziwej bazy działa, `tests.test_store` przechodzi.
2. **`radar/crawl/`** (nowy pakiet, jeszcze bez testów):
   - `__init__.py`: opis pakietu;
   - `fetcher.py`: `Fetcher` (robots.txt przez `urllib.robotparser`, opóźnienie na host z uwzględnieniem `Crawl-delay`, zapytania warunkowe `If-None-Match`/`If-Modified-Since`, limit 15 MB, wykrywanie wyzwań antybotowych → `blocked`) i `FetchResult` (`status`: ok / not_modified / gone / blocked / robots / error, `kind`: html / pdf / xml / other);
   - `sites.py`: `Site` (id, name, category ∈ nauka/projekty/biznes/administracja, start, owner {name, type, voivodeship}, use_sitemap, include/exclude/follow jako regexy, max_pages, max_depth, interval_hours, revisit_days, delay, keep_all, min_score, enabled) i `load_sites()` z `config/sites.json` (albo `$RADAR_SITES`);
   - `frontier.py`: `canonical_url`, `in_scope`, `parse_sitemap`, `enqueue`, `due_pages`, `update_page` (kolejka w `crawl_pages`);
   - `extract.py`: własny parser HTML (główna treść z `<article>`/`<main>`, pomija nav/header/footer/cookies/menu, odrzuca bloki złożone głównie z linków), metadane, JSON-LD, `<time>`, linki; `extract_pdf` (pypdf opcjonalnie); `published_date`, `modified_date`, `best_title`, `description`. Sprawdzone ręcznie na przykładowym HTML.
   - `classify.py`: słowniki sygnałów (innovation, project, offer, event, negative) na tekście po `fold()`, `page_type` (technology_offer / project / event / document / news / other), `prefilter_score`, decyzja `keep` z powodem;
   - `normalize.py`: `build_record(site, page, signals, ...)` → `radar.record/v1`: `source = web_<site_id>`, `record_id` = slug + sha1(URL), organizacje z konfiguracji i ze wzorców form prawnych, województwa, okres i kwoty z fraz, `extra` (category, page_type, signals, published), `quality`, `provenance`. **Jeszcze nieuruchamiany**: sprawdź, czy `parse_period(None).as_dict()` i `parse_money` zwracają oczekiwane typy.

### Sesje równoległe (zatrzymane, bez commitów)

- `claude/vigorous-thompson-a04a91` (konektory OpenAlex, Biblioteka Nauki, RAD-on) i `claude/exciting-brattain-b4c916` (EPO, CORDIS, FE, UPRP) zostały zatrzymane przed pierwszym commitem. Ich zakres jest poniżej w krokach 4 i 5.

## Pozostałe kroki

1. **`radar/crawl/crawler.py`**: `crawl_site(conn, site, fetcher, *, max_pages=None, raw_root=Path("data/raw/web"), dry_run=False) -> stats`:
   - zapis witryny w `crawl_sites`;
   - adresy startowe w kolejce z `depth=0`; przy `use_sitemap` sitemapy z `robots.txt` i `/sitemap.xml` (do 5 plików, do 2000 adresów w zakresie) z `depth=1`;
   - pętla po `due_pages` w budżecie `max_pages`, z uwzględnieniem zapisanych `etag`/`last_modified`;
   - obsługa wyników:
     - `robots`: pominięta, kolejna próba za 30 dni;
     - `blocked`: status `blocked`; blokada strony startowej zatrzymuje witrynę;
     - `error`: ponowna próba za 1 dzień;
     - `gone`: `misses += 1`; po dwóch próbach status `gone` i `store.mark_removed` dla `record_id`;
     - `not_modified`: tylko nowy `next_due`;
     - `ok`: ekstrakcja, linki w zakresie do kolejki z `depth + 1` (do `max_depth`); strony z `follow` tylko do linków; ten sam `content_hash` co poprzednio oznacza brak zmian; poza tym `classify` → `build_record` → surowa treść do `data/raw/web/<site>/<sha16>.html.gz` (wersje nie nadpisują się) → `store.upsert_source(conn, site.source, [rec], mark_removed=False, category=site.category)`.
   - `next_due`: strony startowe i listy co `interval_hours`, rekordy co `revisit_days`, pominięte co `2 × revisit_days`;
   - `conn.commit()` po każdej stronie;
   - `crawl_due(conn, sites, ...)` uruchamia witryny, którym minął termin;
   - `--dry-run` działa na bazie `:memory:` i wypisuje, co zostałoby rekordem i dlaczego.
2. **`radar/crawl/__main__.py`**: `python -X utf8 -m radar.crawl [--site ID ...] [--max-pages N] [--dry-run] [--db] [--config]` oraz `python -X utf8 -m radar.crawl sites` (stan witryn: ostatnie przejście, strony, rekordy, błędy, blokady).
3. **`config/sites.json`**: kilkanaście witryn, po kilka na kategorię, np.:
   - CTT i aktualności uczelni (Politechnika Rzeszowska, Uniwersytet Rzeszowski);
   - parki i inkubatory (Podkarpacki Park Naukowo-Technologiczny);
   - instytucje finansujące (PARP, sekcje projektów i aktualności);
   - samorządy (Urząd Marszałkowski Woj. Podkarpackiego, Rzeszów: projekty, raporty).
   Każdą witrynę dodawaj dopiero po sprawdzeniu `robots.txt` i struktury (`--dry-run --max-pages 20`). Ustaw `include`/`follow`, żeby nie zbierać całych portali.
4. **Konektory nauki** (wzorzec `radar/sources/ncbr.py` i `interreg.py`: `RawStore` + `harvest` + `main` z `--out --csv --raw-dir --offline --limit`):
   - `radar/crawl/oai.py` (klient OAI-PMH) i `radar/sources/bibliotekanauki.py` (`https://bibliotekanauki.pl/api/oai/articles`);
   - `radar/sources/openalex.py` (filtr `institutions.country_code:PL`, abstrakt z `abstract_inverted_index`, bez danych użytkownika w `mailto`);
   - `radar/sources/radon.py` (RAD-on `polon/projects` po `token`, lokalny filtr NCN/NCBR, słownik instytucji).
   Fixture z realnej, małej odpowiedzi i testy bez sieci.
5. **Konektory projektów i patentów** (ten sam wzorzec):
   - przywrócić `radar/sources/epo.py` z `5f6f6bf` (bez zmian GUI/README z tamtego commita);
   - `cordis.py`;
   - `fe_projects.py` (albo import z `data/import/fe/`);
   - `uprp_import.py` (tylko import ręcznego eksportu z `data/import/uprp/`, zero zapytań do UPRP).
6. **Rejestr źródeł w `radar/refresh.py`**: jedna lista `Source(id, source_id, category, kind api/web/import, interval_hours, run, writes_db)` zamiast słowników `SOURCES`, `SOURCE_IDS`, `OUTPUTS`. Do tego:
   - ogólny adapter dla konektorów z `main(argv)`;
   - źródło `web` wywołujące `crawl_due`;
   - kategorie: Interreg i NCBR → `projekty`;
   - flaga `--due-only` (pomija źródła przed terminem według ostatniego wpisu w `refresh_runs`) i `--category`;
   - w `load_into_db` przekazywać `category`, a `force_removal=args.force`.
7. **Scheduler w Dockerze** (`radar/container.py`): budzenie co `REFRESH_TICK_MINUTES` (domyślnie 60) i `refresh --due-only`. W `Dockerfile` `ARG WITH_PDF=1` → `pip install pypdf` oraz kopiowanie `config/`. W `docker-compose.yml` wolumen `./config:/app/config`.
8. **GUI**: filtr kategorii, liczniki kategorii w `/api/meta`, rodzaj strony i sygnały w szczegółach rekordu.
9. **Testy** (unittest, bez sieci):
   - `tests/test_crawl_extract.py` (fixture HTML: artykuł z JSON-LD, strona z menu/stopką/cookies, strona pusta);
   - `tests/test_crawl_classify.py`;
   - `tests/test_crawl_frontier.py` (kanonizacja, zakres, robots, sitemap);
   - `tests/test_crawler.py` (podstawiony opener: 304, dwa 404 → usunięcie, blokada, limit stron, `--dry-run`);
   - `tests/test_store.py`: migracja v1 → v2, `removal_skipped`;
   - `tests/test_refresh.py`: harmonogram `--due-only`.
10. **Dokumentacja**: nowy `docs/zrodla.md` (każde źródło z zadania → sposób, częstotliwość, licencja, ograniczenia, jak dodać witrynę) oraz aktualizacja `README.md`, `docs/docker.md`, `docs/odswiezanie-danych.md`.

## Weryfikacja

- Testy:
  ```powershell
  python -X utf8 -m unittest discover -s tests -t .
  ```
- Przegląd każdej witryny (tytuły, daty, organizacje, powody odrzucenia):
  ```powershell
  python -X utf8 -m radar.crawl --site <id> --max-pages 20 --dry-run
  ```
- Odświeżanie dwa razy: drugie przejście ma się skończyć 304 / brakiem zmian i `added=0`:
  ```powershell
  python -X utf8 -m radar.refresh
  ```
- Rekordy we wszystkich czterech kategoriach:
  ```powershell
  python -X utf8 -m radar.store stats
  ```
- Docker: `docker compose up -d --build`. Logi `scheduler` mają pokazywać źródła uruchamiane według terminów, GUI ma filtrować po kategorii.
- Źródła zablokowane widać w `refresh_runs` jako `blocked`, a ich opis jest w `docs/zrodla.md`.

## Zasady pracy

- Commit i push tylko na prośbę użytkownika. Na koniec commita stopka `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Przy edycji plików z polskimi znakami używaj narzędzia Edit, a nie skryptów `python - <<EOF` z podmianą tekstu (w Git Bash na Windows psują się ukośniki i kodowanie).
- Uruchamiaj Pythona z `-X utf8`.
