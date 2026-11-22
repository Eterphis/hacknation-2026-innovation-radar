# issue-31 / etap 5: test obciążeniowy 50 rps i cache API

- **Agent / model:** Claude Code (claude-opus-5-5)
- **Branch / commits:** `feat/issue31-jakosc-ui`, commit „perf(api): …” (etap 5)
- **Date:** 2026-11-22 03:50

## Goal
Issue #31, zadanie 4: locust 50 rps na `/api/match`, `/api/ideas`, `/api/clusters`, `/api/cards/{id}` na profilu
`public` (2 vCPU / 4 GB), wynik i wąskie gardła tutaj, cache tam, gdzie pomiar pokaże potrzebę.

## What was done
- `loadtest/locustfile.py` (locust 2.47.0, `loadtest/requirements.txt`): użytkownik w `on_start` pobiera `card_id`
  z `/api/ideas` i role z `/api/personas`; zadania z wagami: `/api/match` 4 (losowa rola, województwo, 0–3 sektory,
  budżet, etap, cel), `/api/ideas` 4 (8 zestawów faset, w tym bez filtrów), `/api/cards/{id}` 3, `/api/clusters` 2
  (3 tryby). Odstęp 0,8–1,6 s.
- `loadtest/compose.limits.yml`: api 1,2 CPU / 2 GB, postgres 0,5 CPU / 1,25 GB, rabbitmq 0,3 CPU / 0,75 GB
  (razem 2,0 CPU / 4 GB). Workery i beat dostały małe limity (0,25 / 0,25 / 0,1 CPU), bo po zasileniu nie mają pracy.
- **Cache** (`app/radar/api/cache.py`, w procesie): klucz = endpoint + znormalizowane parametry, ważny tylko przy tej
  samej *wersji danych* (jedno tanie zapytanie agregujące: liczba i max id kart, suma polubień i ocen, liczniki
  decyzji, liczba rekordów i ostatni `updated_at`) i TTL 300 s. Nowa karta z potoku, polubienie i decyzja operatora
  zmieniają wersję, więc nic nie jest nieaktualne. `reset_api_cache()` w autouse fixture `app/tests/conftest.py`.
  - `/api/match`: w cache jest „korpus” (wycena `business_case`, etykiety i `idea_dict` każdego rekordu, niezależne od
    profilu); punktacja profilu zostaje liczona przy każdym zapytaniu.
  - `/api/ideas`: cała odpowiedź per parametry; dodatkowo naprawione N+1 (`contains_eager(Record.card)`).
  - `/api/clusters`: wcześniej słownik z TTL 10 min bez unieważniania (nowa karta była niewidoczna do 10 min),
    teraz ten sam mechanizm z wersją danych.
  - `/api/cards/{id}`: bez cache (licznik polubień musi być zawsze aktualny; 2 zapytania, ~6–10 ms).
- Uvicorn: **bez zmian** (1 proces). Po poprawce api zużywa ~0,47 rdzenia przy 56 rps przy limicie 1,2, więc
  `--workers 2` nie był potrzebny; Helm i k3d bez zmian.

## Evidence
Sprzęt: Windows 11, Docker Desktop 29.9.3 (VM WSL2: 12 vCPU, 7,6 GB), limity z `compose.limits.yml` sprawdzone
`docker inspect` (api: NanoCpus 1,2e9, Memory 2 GiB). Dane: `docker compose exec -T api radar demo` (23 pomysły demo).
Locust na tym samym hoście, ruch bezpośrednio do api `:8000` (Caddy z profilu public działał, ale dodaje tylko TLS
i kompresję).

```powershell
$env:RADAR_DEMO_MODE=1; docker compose --profile public -f docker-compose.yml -f loadtest/compose.limits.yml up -d --build
docker compose exec -T api radar demo
loadtest/.venv/Scripts/locust -f loadtest/locustfile.py --host http://localhost:8000 --headless -u 60 -r 10 -t 3m --csv .house/reports/load/przed
loadtest/.venv/Scripts/locust -f loadtest/locustfile.py --host http://localhost:8000 --headless -u 70 -r 10 -t 3m --csv .house/reports/load/po
```

**Przed** (origin/main + etapy 1–4, 60 użytkowników, 3 min): serwer nasycony, generator dostawał tyle, ile api oddało.

| endpoint | zapytań | błędy | p50 | p95 | p99 | rps |
|---|---|---|---|---|---|---|
| `/api/match` | 1100 | 0 | 2300 ms | 4000 ms | 5100 ms | 6,11 |
| `/api/ideas` | 1061 | 0 | 2200 ms | 3900 ms | 4900 ms | 5,89 |
| `/api/cards/{id}` | 751 | 0 | 1400 ms | 3000 ms | 4000 ms | 4,17 |
| `/api/clusters` | 554 | 0 | 250 ms | 1100 ms | 1600 ms | 3,08 |
| **razem** | 3586 | **0** | 1700 ms | 3700 ms | 4700 ms | **19,9** |

**Po** (70 użytkowników, 3 min):

| endpoint | zapytań | błędy | p50 | p95 | p99 | rps |
|---|---|---|---|---|---|---|
| `/api/match` | 3042 | 0 | 22 ms | 68 ms | 160 ms | 16,97 |
| `/api/ideas` | 3084 | 0 | 20 ms | 68 ms | 160 ms | 17,21 |
| `/api/cards/{id}` | 2381 | 0 | 20 ms | 70 ms | 170 ms | 13,28 |
| `/api/clusters` | 1515 | 0 | 20 ms | 62 ms | 140 ms | 8,45 |
| **razem** | 10162 | **0** | 21 ms | 74 ms | 190 ms | **56,7** |

Zużycie w połowie przebiegu „po” (`docker stats`): api 47% (0,47 rdzenia z 1,2), postgres 5%, rabbitmq 0,3%.
Przebieg pośredni z 60 użytkownikami: 48,9 rps, p50 21 ms (limit generatora, nie serwera: 60 × ~0,83 zapytania/s
z rozbiegiem). Surowe CSV: `.house/reports/load/przed_*.csv`, `.house/reports/load/po_*.csv`.

**Profilowanie** (`loadtest/sql_profile.py`: licznik `before_cursor_execute` SQLAlchemy + czas jednego żądania,
SQLite, pierwsze / drugie wywołanie):

| endpoint | przed: SQL, czas | po: 1. wywołanie | po: 2. wywołanie |
|---|---|---|---|
| `/api/match` (samorząd, pomorskie) | 24 SQL, 62–135 ms | 3 SQL, 42 ms | 2 SQL, 8 ms |
| `/api/ideas?limit=24` | 32 SQL, 54–97 ms | 11 SQL, 29 ms | 2 SQL, 8 ms |
| `/api/clusters?mode=tematy` | 24 SQL, 78 ms (potem 0 z TTL) | 26 SQL, 35 ms | 2 SQL, 6 ms |
| `/api/cards/1` | 2–3 SQL, 10–62 ms | 3 SQL, 27 ms | 2 SQL, 6 ms |

Testy: `app/tests/test_api_cache.py` (drugie wywołanie robi tylko 2 zapytania wersji, wynik z cache = wynik
policzony po `reset_api_cache()`, nowa karta z `harvest` zmienia `total` w match/ideas/clusters bez ręcznego
unieważniania, polubienie widoczne od razu w `/api/cards/{id}` i na liście). Pełny `pytest` w `app/`: 140 passed,
1 skipped.

## Result vs acceptance
- 50 rps łącznie przez ≥ 3 min, `failures = 0`: **pass** (56,7 rps, 0 błędów, 3 min).
- p50/p95/p99 per endpoint zapisane: **pass** (tabele wyżej, CSV).
- pomiar bazowy → profilowanie → poprawka → drugi pomiar: **pass**.
- cache z `reset_*()` w conftest, świeże polubienia, testy pytest: **pass**.

## Tested and did not work
- Bez cache sufit to ~20 rps: `/api/match` i `/api/ideas` po ~50–60 ms CPU każde w jednym procesie z limitem
  1,2 CPU; GIL nie pozwala wykorzystać więcej przez wątki threadpoola FastAPI.

## Next
- Pomiar na 23 rekordach demo. Na prawdziwych danych (setki–tysiące kart) zimne wywołanie `/api/match` i klastrów
  będzie droższe; cache liczy korpus raz na wersję danych, ale potok, który co chwilę dodaje kartę, będzie go często
  unieważniał. Wtedy warto rozważyć przeliczanie korpusu w tle albo wersję podbijaną tylko przez etap `score`.
- `py-spy` nie był użyty (host Windows, obraz bez py-spy); profil oparto na liczniku SQL i czasie żądania.
- Workery Celery w spoczynku dobijają do swoich limitów 0,25 CPU (healthcheck `celery inspect ping`); na VPS 2 vCPU
  to realny koszt tła, do sprawdzenia osobno.
- CI ma tylko dymny `load-smoke` (30 s, 10 użytkowników, `--exit-code-on-error 1`), bez progu rps.
