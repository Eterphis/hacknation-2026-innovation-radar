# Radar innowacji w Dockerze

Jeden obraz, dwa kontenery:

| Kontener | Co robi |
|---|---|
| `gui` | przeglądarka danych na http://localhost:8765 (wyszukiwanie, szczegóły rekordu, historia zmian) |
| `scheduler` | odświeża dane z Interreg i NCBR zaraz po starcie, a potem co 24 h (`radar.refresh`) |

Oba korzystają z katalogu `./data` na Twoim komputerze: tam są surowe pliki, wyniki JSONL i baza `data/radar.db`. Usunięcie kontenerów niczego nie kasuje.

## Wymagania

- Docker Desktop (Windows / macOS) albo Docker Engine z Compose v2 (Linux).
- Dostęp do internetu przy pierwszym odświeżeniu.

## Start

```powershell
docker compose up -d --build
```

Potem otwórz http://localhost:8765. Przy pierwszym uruchomieniu baza jest pusta: `scheduler` pobiera dane od razu (Interreg kilka sekund, NCBR około 5 minut, crawler stron kilkanaście minut, bo na każdy host wysyła najwyżej jedno zapytanie na 2 s). Potem co godzinę sprawdza terminy i uruchamia tylko źródła, którym minął. Strona pokazuje nowe rekordy po odświeżeniu przeglądarki, restart nie jest potrzebny.

Witryny crawlera są w `config/sites.json`, podmontowanym do kontenerów: po zmianie pliku nie trzeba przebudowywać obrazu.

Postęp pobierania:

```powershell
docker compose logs -f scheduler
```

Zatrzymanie (dane zostają w `./data`):

```powershell
docker compose down
```

## Jednorazowe polecenia

Każde uruchamia się w nowym, tymczasowym kontenerze z tym samym katalogiem `./data`.

Odśwież dane teraz, nie czekając na harmonogram:

```powershell
docker compose run --rm gui refresh
```

Pobierz wszystko od nowa:

```powershell
docker compose run --rm gui refresh --force
```

Sprawdź, co by zostało pobrane, bez zapisywania:

```powershell
docker compose run --rm gui refresh --dry-run
```

Odbuduj bazę z zapisanych plików, bez sieci:

```powershell
docker compose run --rm gui refresh --offline
```

Źródła z rejestru, ich kategorie i terminy:

```powershell
docker compose run --rm gui refresh --list
```

Przegląd jednej witryny crawlera bez zapisu do bazy (co byłoby rekordem i dlaczego):

```powershell
docker compose run --rm gui crawl --site ur_ctt --max-pages 20 --dry-run
```

Stan witryn crawlera (strony, rekordy, błędy, blokady):

```powershell
docker compose run --rm gui crawl sites
```

Policz karty innowacji dla nowych i zmienionych rekordów:

```powershell
docker compose run --rm gui cards --stale
```

Podsumowanie bazy, wyszukiwanie i eksport:

```powershell
docker compose run --rm gui store stats
```

```powershell
docker compose run --rm gui store search "pompa ciepla"
```

```powershell
docker compose run --rm gui store export --source ncbr_sukcesy --out data/eksport/ncbr.jsonl
```

Powłoka w kontenerze:

```powershell
docker compose run --rm gui shell
```

Wszystkie opcje `refresh` opisuje [odswiezanie-danych.md](odswiezanie-danych.md).

## Ustawienia (`.env`)

Skopiuj `.env.example` do `.env` i zmień, co trzeba. Bez pliku `.env` działa na wartościach domyślnych.

```powershell
Copy-Item .env.example .env
```

| Zmienna | Domyślnie | Opis |
|---|---|---|
| `RADAR_PORT` | `8765` | port przeglądarki na komputerze |
| `REFRESH_TICK_MINUTES` | `60` | co ile minut `scheduler` sprawdza terminy i uruchamia źródła, którym minął (`refresh --due-only`) |
| `REFRESH_ARGS` | (puste) | dodatkowe opcje każdego odświeżenia, np. `--delay 2` |
| `ANTHROPIC_API_KEY` | (puste) | klucz Claude dla kart; bez niego karty liczone są offline, na regułach |
| `RADAR_LLM` | `auto` | `auto` / `claude` / `offline` |

Po zmianie `.env`:

```powershell
docker compose up -d
```

Obraz bez biblioteki `anthropic` (mniejszy, tylko tryb offline):

```powershell
docker compose build --build-arg WITH_LLM=0
```

## Kopia zapasowa i reset

- **Kopia:** zatrzymaj kontenery (`docker compose down`) i skopiuj `data/radar.db`. Do pełnej kopii wystarczy cały katalog `data/`.
- **Reset bazy:** zatrzymaj kontenery, usuń `data/radar.db*` i uruchom `docker compose run --rm gui refresh --offline`. Baza zostanie odbudowana z zapisanych plików, ale historia zmian zacznie się od nowa.
- **Wszystko od zera:** usuń cały katalog `data/` i uruchom `docker compose up -d`.

## Jak to działa

- Obraz `python:3.12-slim`, sam kod radaru (biblioteka standardowa), opcjonalnie `anthropic` (`WITH_LLM=1`) i `pypdf` do tekstu z PDF (`WITH_PDF=1`, domyślnie włączone). Działa jako użytkownik bez uprawnień administratora (uid 1000).
- Punkt wejścia: [`radar/container.py`](../radar/container.py). Komendy: `gui`, `scheduler`, `refresh`, `crawl`, `cards`, `store`, `shell`.
- `scheduler` budzi się co `REFRESH_TICK_MINUTES` (domyślnie 60) i uruchamia `refresh --due-only`. Terminy źródeł są w rejestrze `radar/refresh.py`, a terminy witryn w `config/sites.json`.
- Baza SQLite pracuje w trybie WAL: `gui` czyta, gdy `scheduler` pisze.
- Blokada `data/.refresh.lock` zapisuje nazwę kontenera, więc ręczne `refresh` nie wystartuje, gdy `scheduler` właśnie odświeża. Poczeka na następne uruchomienie albo zakończy się komunikatem.
- `gui` ma healthcheck (`/api/meta`). Stan kontenerów pokazuje `docker compose ps`.

## Problemy

| Objaw | Rozwiązanie |
|---|---|
| `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine` | Docker Desktop nie jest uruchomiony: włącz go, poczekaj, aż `docker info` zadziała, i powtórz polecenie |
| `no configuration file provided: not found` | uruchamiasz polecenie w katalogu bez `docker-compose.yml`; przejdź do katalogu repozytorium z tymi plikami |
| `port is already allocated` | ustaw inny `RADAR_PORT` w `.env` |
| `429 Too Many Requests` przy budowaniu (`registry-1.docker.io`) | Docker Hub ogranicza pobrania; zbuduj z tego samego obrazu w lustrze Google: `docker compose build --build-arg BASE_IMAGE=mirror.gcr.io/library/python:3.12-slim`, potem `docker compose up -d` |
| `odświeżanie już trwa` | inne odświeżanie właśnie pracuje; poczekaj albo sprawdź `docker compose logs scheduler` |
| Linux: `Permission denied` przy zapisie do `./data` | `sudo chown -R 1000:1000 data` |
| Strona pusta po starcie | pierwsze pobieranie jeszcze trwa: `docker compose logs -f scheduler` |
