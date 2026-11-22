# Test obciążeniowy na prawdziwych danych (2026-11-22)

**Dane:** 1699 rekordów, 1247 ocenionych kart (NCBR, Kohesio, OpenAIRE, uczelnie, zgłoszenia), nie 23 rekordy demo jak w `load.md`.
**Profil:** `loadtest/compose.limits.yml`, czyli api 1,2 CPU / 2 GB, postgres 0,5 CPU / 1,25 GB, rabbitmq 0,3 CPU (jak VPS 2 vCPU / 4 GB).
**Ruch:** `loadtest/locustfile_real.py` to wszystko, co robi UI: Przegląd (`/api/insights`), mapa, rolki, dopasowanie, listy,
klastry, karta i opcjonalnie polubienia (`LIKES=1`: polub i cofnij). Użytkownik locusta wysyła ~1 zapytanie na 1,2 s.

| przebieg | użytk. | rps | błędy | p50 | p95 | p99 |
|---|---|---|---|---|---|---|
| przed poprawkami, same odczyty | 70 | **3,2** | 38 (7%) | 7,1 s | 53 s | 69 s |
| single-flight i cache dla Przeglądu, mapy, rolek i person | 70 | **53,4** | 0 | 15 ms | 110 ms | 1,6 s |
| jw., z polubieniami (polubienie czyściło cały cache) | 150 | 6,9 | 0 | 7,3 s | 54 s | 85 s |
| polubienia poza wersją danych (nakładka liczników) | 150 | **110,6** | 0 | 33 ms | 590 ms | 6,7 s |

CSV: `.house/reports/load/real*_stats.csv`. Pamięć API: 2 GiB z 2 GiB (limit) przed poprawką, ~550 MB po.

## Co było nie tak
1. **Stampede:** przy pustym cache każdy z 70 wątków liczył ten sam wynik naraz (klastry, korpus dopasowania). CPU 100%,
   pamięć na limicie, czasy w dziesiątkach sekund. Teraz liczy jeden wątek, a reszta czeka na wynik (`radar.api.cache`).
2. **Przegląd, mapa, rolki i persony bez cache:** `/api/insights` czyta wszystkie karty przy każdym wejściu na stronę główną
   (1,6 s na zimno). Teraz jest w cache z wersją danych (24 ms).
3. **Polubienie unieważniało wszystko:** suma polubień była częścią wersji danych, więc każde serduszko kazało przeliczyć
   wszystkie listy dla wszystkich. Teraz polubienia nie zmieniają wersji. Liczniki w odpowiedziach z cache są nadpisywane z małej
   mapy `card_id -> likes`, odczytywanej tylko wtedy, gdy suma polubień się zmieniła. Liczby zostają aktualne,
   ale kolejność „wg polubień” odświeża się dopiero przy zmianie danych lub po 5 min (TTL).
4. **Zapytanie o wersję przy każdym żądaniu:** teraz najwyżej co 2 s na proces (`VERSION_TTL`).

## Ile osób naraz
Prawdziwy użytkownik wysyła średnio 0,15–0,3 zapytania/s: wejście na stronę to 2–4 zapytania, potem 10–30 s czytania.
110 rps przy p95 < 0,6 s to więc **ok. 400–700 osób aktywnych jednocześnie** na profilu 2 vCPU / 4 GB.
Ostatni przebieg był ograniczony generatorem, a nie serwerem (API: jeden proces uvicorn na 1,2 CPU).
Większy ruch obsłuży więcej procesów (`--workers`) albo replik (Helm, HPA). Bielik i nagrania nie są na ścieżce zapytań.
