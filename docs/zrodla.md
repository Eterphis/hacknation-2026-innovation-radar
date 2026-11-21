# Źródła danych

Zadanie (PDF PCI, §7) wymienia cztery kategorie źródeł i wymaga cyklicznej aktualizacji bazy. Ten dokument mówi, skąd i jak radar bierze dane w każdej kategorii, jak często je odświeża i czego nie pobiera (z powodu).

Wszystko jest zbierane **bez LLM**: struktura HTML, JSON-LD i OpenGraph, słowniki sygnałów, wyrażenia regularne. Każdy rekord ma format `radar.record/v1` i trafia do bazy `data/radar.db` z historią zmian i kategorią.

## Zasady pobierania

- `robots.txt` jest respektowany, w tym `Crawl-delay`.
- Na jeden host idzie najwyżej jedno zapytanie na 2 s (więcej, jeśli witryna tak ustawi).
- User-Agent: `innovation-radar-harvester/0.1` (z `radar/http.py`).
- Zapytania warunkowe (`If-None-Match`, `If-Modified-Since`): niezmieniona strona nie jest pobierana ponownie, gdy serwer to obsługuje. Jeśli nie obsługuje, zmianę wykrywa hash treści i nie powstaje nowa wersja rekordu.
- **Żadnego obchodzenia zabezpieczeń.** Strona z CAPTCHA, wyzwaniem JS albo ochroną antybotową dostaje status `blocked`. Blokada strony startowej zatrzymuje całą witrynę. Źródło jest wtedy opisane poniżej, a w konfiguracji ma `enabled: false`.
- Strona, która dwa razy z rzędu odpowie 404/410, jest uznana za usuniętą. Jej rekord dostaje `removed_at` i zostaje w bazie z historią.
- Gdy z jednego pobrania źródła zniknęłaby ponad połowa rekordów, radar nie oznacza ich jako usuniętych: to raczej zmiana formatu strony niż prawdziwe usunięcie. Wymusza się to flagą `--force`.

## Źródła według kategorii z zadania

Częstotliwość to termin w rejestrze `radar/refresh.py` (`REGISTRY`) albo w `config/sites.json` (`interval_hours` dla stron list, `revisit_days` dla rekordów). Scheduler sprawdza terminy co godzinę.

### Nauka i technologie

| Źródło z zadania | Jak | Częstotliwość | Uwagi |
|---|---|---|---|
| Google Scholar | zamiennik: **OpenAlex API** (prace z afiliacją PL) i **Biblioteka Nauki** (OAI-PMH) | co 7 dni | Google Scholar nie ma API, a regulamin zabrania scrapowania. Konektory: `radar/sources/openalex.py`, `radar/sources/bibliotekanauki.py` |
| Polskie uczelnie | crawler: `prz_aktualnosci` (PRz: nauka, współpraca z gospodarką), `ur_aktualnosci` (UR) | listy co 24 h, rekordy co 30 dni | PRz: kategorie aktualności z filtrem. UR: ogólne aktualności, więc filtr innowacji odrzuca większość wpisów |
| Instytuty badawcze | **RAD-on** (instytucje z REGON/NIP/typem, projekty z abstraktami): `radar/sources/radon.py` | co 7 dni | Sieć Łukasiewicz: wyłączona na czas przerwy technicznej serwisu (2026-11-21) |
| Bazy patentowe | **EPO** (zgłoszenia z polskimi zgłaszającymi): `radar/sources/epo.py`; **UPRP**: tylko import ręcznego eksportu (`radar/sources/uprp_import.py`, pliki w `data/import/uprp/`) | EPO co 7 dni, import co 24 h | UPRP blokuje automaty: radar nie wysyła do niego żadnych zapytań |
| PBN, PAN dLibra, BazTOL | brak | – | PBN wymaga tokenu, PAN dLibra stawia wyzwanie JS (zastąpiona Biblioteką Nauki), BazTOL to katalog linków |

### Projekty badawcze i innowacyjne

| Źródło z zadania | Jak | Częstotliwość | Uwagi |
|---|---|---|---|
| NCBR | `radar/sources/ncbr.py` (wyszukiwarka sukcesów beneficjentów) | co 24 h | strony szczegółów raz pobrane są brane z dysku |
| NCN | projekty NCN z RAD-on (`radar/sources/radon.py`, filtr finansującego) | co 7 dni | |
| PARP, Fundusze Europejskie | lista projektów FE 2021–2027 (`radar/sources/fe_projects.py`) oraz crawler `fe_podkarpacie_projekty` (projekty Województwa Podkarpackiego) | konektor co 7 dni; crawler: listy co 72 h, rekordy co 30 dni | strona PARP ma ochronę antybotową, więc projekty PARP trafiają przez listę projektów FE |
| CORDIS | zrzuty projektów Horizon Europe i H2020, organizacje z PL (`radar/sources/cordis.py`) | co 7 dni | |
| Interreg | `radar/sources/interreg.py` (wykaz projektów XLSX) | co 24 h | plik pobierany tylko wtedy, gdy na stronie pojawi się nowy |

### Startupy i biznes

| Witryna (`config/sites.json`) | Co | Częstotliwość |
|---|---|---|
| `ur_ctt` | Uniwersyteckie Centrum Transferu Technologii UR: aktualności, broker technologii | listy co 48 h, rekordy co 30 dni |
| `dolina_lotnicza` | klaster Dolina Lotnicza: aktualności i projekty | listy co 48 h, rekordy co 30 dni |
| `arp_innowacje` | Agencja Rozwoju Przemysłu: programy innowacji, projekty kosmiczne, produkty finansowe | listy co 7 dni, rekordy co 60 dni |

Wyłączone (sprawdzone 2026-11-21, nie obchodzimy):

| Witryna | Powód |
|---|---|
| PARP (`parp`) | ochrona antybotowa (strona wyzwania) |
| PFR (`pfr`) | ochrona antybotowa (HTTP 403 ze stroną wyzwania) |
| RARR (`rarr`) | `robots.txt` zabrania automatom dostępu |
| CTT Politechniki Rzeszowskiej (`prz_ctt`) | HTTP 403 dla automatów; aktualności o współpracy z gospodarką są w `prz_aktualnosci` |
| PPNT Aeropolis (`aeropolis`) | HTTP 406 dla automatów (filtr serwera); do ponownego sprawdzenia |

### Administracja i edukacja

| Witryna (`config/sites.json`) | Co | Częstotliwość |
|---|---|---|
| `umwp` | Samorząd Województwa Podkarpackiego: aktualności działów (gospodarka, rozwój regionalny, edukacja, środowisko, transport i inne) | listy co 48 h, rekordy co 30 dni |
| `mielec` | Urząd Miejski w Mielcu: fundusze zewnętrzne, strategia, rewitalizacja | listy co 7 dni, rekordy co 60 dni |
| `mrit_wiadomosci` | Ministerstwo Rozwoju i Technologii: wiadomości (tylko strony z datą publikacji) | listy co 24 h, rekordy co 60 dni |

Wyłączone: Urząd Miasta Rzeszowa (`rzeszow`): erzeszow.pl i rzeszow.pl odpowiadają automatom HTTP 503; do ponownego sprawdzenia.

Konektory, których jeszcze nie ma w repozytorium, rejestr pomija bez błędu. `python -X utf8 -m radar.refresh --list` pokazuje, które źródła są aktywne i kiedy mają termin.

## Jak crawler decyduje, co jest rekordem

1. Ze strony wyciągana jest główna treść: `<article>`/`<main>`, bez menu, stopek, banerów cookies i bloków złożonych głównie z linków. Do tego metadane: tytuł, opis, data z JSON-LD, OpenGraph albo `<time>`.
2. Słowniki sygnałów (innowacja, projekt, oferta technologiczna, wydarzenie, sygnały negatywne) dają wynik i rodzaj strony. Strona zostaje rekordem, gdy wynik przekracza `min_score` witryny. Strony serwisowe (polityka prywatności, przetargi, rekrutacja) i za krótkie są odrzucane.
3. Każda decyzja ma zapisany powód (`provenance.keep_reason`, `crawl_pages.reason`). W GUI widać go w sekcji „Ocena crawlera”.

To jest filtr wstępny, a nie ocena innowacyjności. Ocenę robi później karta innowacji (`radar.card`).

## Jak dodać witrynę

1. Sprawdź `robots.txt` witryny i to, czy nie ma ochrony antybotowej.
2. Dopisz wpis w `config/sites.json`. Pola opisuje `radar/crawl/sites.py`, najważniejsze to:
   - `id` (małe litery, cyfry, `_`), `name`, `category` (`nauka` / `projekty` / `biznes` / `administracja`);
   - `start`: strony list (aktualności, projekty);
   - `include`: wyrażenia regularne na ścieżce stron, które mogą być rekordami;
   - `follow`: listy i ich kolejne strony, z których tylko zbieramy linki;
   - `exclude`: ścieżki do pominięcia;
   - `owner`: wydawca strony (nazwa, typ, województwo);
   - `min_score` (domyślnie 2.0), `require_date` (odrzuca strony bez daty, np. strony-węzły portali);
   - `max_pages`, `max_depth`, `interval_hours`, `revisit_days`.
3. Przejrzyj wynik bez zapisu do bazy:
   ```powershell
   python -X utf8 -m radar.crawl --site <id> --max-pages 20 --dry-run
   ```
   Dla każdej strony widać decyzję (REKORD / pomiń), tytuł, datę, organizacje i powód. Zawęź `include`/`follow`, jeśli crawler wchodzi w niepotrzebne części portalu.
4. Uruchom naprawdę i sprawdź stan witryny:
   ```powershell
   python -X utf8 -m radar.crawl --site <id>
   ```
   ```powershell
   python -X utf8 -m radar.crawl sites
   ```

## Licencje i prawa do treści

Kod jest na licencji EUPL-1.2. Pobrane dane (`data/`) nie trafiają do repozytorium, bo warunki ponownego wykorzystania treści ze stron nie są potwierdzone. Każdy rekord ze strony ma w polu `rights` notatkę o tym, skąd pochodzi. Biblioteka `pypdf` (opcjonalna, do tekstu z PDF) jest na licencji BSD, zgodnej z EUPL.
