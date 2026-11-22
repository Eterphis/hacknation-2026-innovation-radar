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
- Kontener `scheduler` od razu pobiera dane (Interreg, NCBR, crawler stron z `config/sites.json` i konektory API), a potem co godzinę sprawdza terminy i uruchamia źródła, którym minął. Po pobraniu wystarczy odświeżyć stronę.
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

## Aplikacja (`app/`, `deploy/helm/`)

Python 3.12: FastAPI (API + UI operatora), Celery + RabbitMQ (jedna kolejka na etap, `acks_late`, DLQ, idempotencja po `(raw_id, stage, content_hash)`), Postgres z migracjami Alembic, router LLM z fallbackiem (`local (Bielik na CPU) → anthropic → openai-compatible → reguły`).

**Źródła danych** to wpisy w [`app/sources.yaml`](app/sources.yaml), nie kod. Wszystkie kończą w jednym `ingest()`:

| Tryb | Typy | Jak |
|---|---|---|
| pull | `rest`, `graphql`, `oaipmh`, `sparql`, `snapshot` | `harvest` z harmonogramu (`schedule_s`) albo przycisk w UI; kursor zapisywany po każdej stronie |
| push | `webhook` | `POST /api/ingest/webhook/<id>`, HMAC-SHA256 w `X-Radar-Signature` (`RADAR_WEBHOOK_SECRET_<ID>`) |
| push | `amqp`, `gcp_pubsub`, `kafka` | `radar consume <id>`; Helm tworzy osobny Deployment na każde takie źródło |
| ręcznie | formularz | `POST /api/ingest/<id>/manual` |

Mapowanie pól to JMESPath + transformacje (`pl_decimal` dla kwot Kohesio, `doi`, `year`, `first`…). Nowy protokół: klasa `PullConnector` + `radar.sources.registry.register()`.

### Uruchomienie

```bash
docker compose up --build          # http://localhost:8000 (RADAR_PORT=8088 gdy port zajęty)
```
Bez kluczy działa tryb demo: snapshoty z `app/samples/` (dane syntetyczne, oznaczone) i heurystyczny „mock” zamiast LLM, oznaczony na każdej karcie. Klucze: `cp .env.example .env`.

Lokalnie bez Dockera: `cd app && python -m venv .venv && .venv/Scripts/pip install -e ".[dev]" && .venv/Scripts/python -m pytest` oraz `radar demo` (wszystko inline, SQLite).

### Kubernetes

```bash
helm install radar deploy/helm/innovation-radar --set image.repository=<registry>/innovation-radar --set image.tag=<tag>
```
`values.yaml`: `workers[]` (grupy kolejek i współbieżność), `sources:` (treść sources.yaml → ConfigMap; źródła push dostają konsumentów), `secrets:` / `existingSecret`, `postgresql.enabled` / `rabbitmq.enabled` (wbudowane albo zewnętrzne), `ingress`, `api.autoscaling`, `localLLM`, `config.embedder`, `config.llmPrices`.

**Lokalnie na k3d** (to samo robi job `k3d` w CI):
```bash
docker build -t innovation-radar:dev app
k3d cluster create radar --agents 1 --wait
k3d image import innovation-radar:dev -c radar
kubectl create secret generic radar-keys --from-literal=RADAR_ANTHROPIC_API_KEY=...   # opcjonalnie
helm install radar deploy/helm/innovation-radar --set image.repository=innovation-radar --set image.tag=dev   --set image.pullPolicy=Never --set existingSecret=radar-keys --wait --timeout 15m
kubectl get pods                                  # wszystkie Ready; Job radar-...-migrate-1 = Alembic
kubectl port-forward svc/radar-innovation-radar-api 8080:80   # http://localhost:8080
```
Publiczny URL: `--set ingress.enabled=true --set ingress.host=<domena>` (k3d ma Traefik: `k3d cluster create radar -p "80:80@loadbalancer"`).

**CI** (`.github/workflows/ci.yml`): pytest obu pakietów (osobne joby, bo oba nazywają się `radar`), `helm lint` i `helm template` (warianty domyślny, z lokalnym LLM i z zewnętrznymi usługami), build obrazu ze smoke testem (`radar migrate` i e5-small offline), push do GHCR z `main`, a w PR instalacja na k3d z czekaniem na Ready i zapytaniem do `/healthz` i `/metrics`.

Zadania do zrobienia: [`.house/tasks/`](.house/tasks/) (T020–T036).

### Główne flow (szczegóły: [`.house/reports/main-flow.md`](.house/reports/main-flow.md))

1. **Wejście danych:** pull/push/formularz, jak wyżej.
2. **Basal** (`app/radar/basal/`, bez LLM, milisekundy na rekord, zwykły vCPU): jedna decyzja *przyjmij / do przeglądu / odrzuć* z powodem oraz etykiety na 7 osiach (sektor PKD, obszar technologii, typ innowacji, typ instytucji, dojrzałość, koszt, województwo) i priorytet w kolejce (`x-max-priority`). Słowniki + podobieństwo do prototypów etykiet w przestrzeni embeddingów + głowa decyzji uczona na decyzjach operatora (`POST /api/basal/train`).
3. **Agent wdrożeniowy** (`app/radar/pipeline/assess.py`, pętla w `agent.py`): model sam wywołuje narzędzia (`find_similar`, `regional_context`, `recipients`, `lookup_registry`) w protokole JSON, który działa także na 1,5B bez natywnego tool calling, i zwraca ścieżki „kto co robi”, ryzyka z mitygacjami i podsumowanie. **Każde twierdzenie musi wskazywać fakt** (`T1…` = wynik narzędzia, `rec:<id>` = rekord zwrócony przez narzędzie, `karta`, `basal`). Kod to sprawdza: zmyślone odnośniki i ścieżki spoza listy wracają raz do modelu, potem są odrzucane. Potem recenzent **„co przemawia przeciw”** (LLM albo reguły, też z odnośnikami), Basal sprawdza spójność, a 6 jawnych kryteriów daje wynik 0–100. Bez modelu działa ta sama pętla z polityką regułową (ten sam kształt, ślad narzędzi w `assessment.agent.trace`).
4. **Prezentacja** (UI w stylu „Zero Interface”): *Przegląd* (trendy, wyróżniające się, najbardziej zaawansowane, gotowe do powielenia, tanie wdrożenia, wymagające dużego budżetu, ukryte perełki, dublowanie prac, luki regionalne, portfel koszt × dojrzałość), *Odkrywaj* (fasety), *Graf* (jak w Obsidianie), *Mapa* (kartogram + macierz województwo × sektor), *Rolki* (jednostronicowe briefy z polubieniami), *Zgłoś* (podgląd Basala na żywo), *Operator*. Wyszukiwanie klawiszem `/`, także głosem tam, gdzie przeglądarka wspiera Web Speech API.

### Lekki model na VPS (bez GPU)

```bash
RADAR_LOCAL_LLM_URL=http://llm:8080/v1 docker compose --profile local-llm up --build
```
llama.cpp server z **Bielik 1.5B v3.0 Instruct GGUF Q8_0** (polski, Apache-2.0, ~1,7 GB, pobierany przy pierwszym starcie). W Helm: `--set localLLM.enabled=true`. Na 4–10 vCPU jedno wywołanie trwa ~1 min (`RADAR_LOCAL_LLM_TIMEOUT_S`, domyślnie 300 s), więc agent na 1,5B nadaje się do kolejki w tle, nie do odpowiedzi na żywo. Cała praca LLM jednej oceny (kroki agenta i recenzent) ma wspólny budżet `RADAR_AGENT_BUDGET_S` (domyślnie 420 s): po jego wyczerpaniu ocenę kończą reguły, a limity zadania `score` w Celery są liczone z budżetu (+60 s miękki, +120 s twardy), więc wolny model nie jest zabijany i powtarzany od zera. Recenzent LLM rusza tylko, gdy zostało co najmniej `RADAR_AGENT_REVIEW_MIN_S` (60 s). Wyniki: `.house/experiments.csv` (agent-eval). Embeddingi: domyślnie `hashing` (numpy, zero pobierań); `RADAR_EMBEDDER=fastembed` = `multilingual-e5-small` (ONNX/CPU, wbudowany w obraz). Progi podobieństwa są kalibrowane osobno dla każdego embeddera (`radar/basal/embed.py`, `CALIBRATION`); próg krawędzi „podobne” dopasowuje się do korpusu (kwantyl podobieństw par w zakresie z kalibracji), więc krótkie rekordy demo i długie prawdziwe opisy dostają podobny odsetek połączeń.

### Ewaluacja (Basal i agent)

```bash
cd app && radar basal-eval --errors                       # trafność Basala na 60 prawdziwych rekordach
cd app && radar basal-eval --log ../.house/experiments.csv # + wpis E-### do dziennika eksperymentów
RADAR_LOCAL_LLM_URL=http://localhost:8081/v1 python eval/agent_eval.py --n 4 --log ../.house/experiments.csv
```
Zbiór testowy [`app/eval/basal_gold.jsonl`](app/eval/basal_gold.jsonl): 32 sukcesy NCBR i 28 projektów Interreg 2021–2027, wylosowane ze stałym ziarnem z wyników harvestera, ręcznie oznaczone (sektor, decyzja, typ instytucji; reguły w `eval/build_testset.py`). W repo są tylko identyfikatory i etykiety. Treść rekordów zostaje w `data/` (licencja nieustalona), więc ewaluacja wymaga lokalnego `data/normalized/`. Wynik **strict** to zgodność z pierwszą etykietą, a **lenient** to trafienie w jedną z etykiet „a|b”, gdy dwie są równie uzasadnione.

### Obserwowalność

```bash
docker compose --profile observability up -d   # Grafana :3000 (dashboard „Radar”), Prometheus :9090, Flower :5555
```
`GET /metrics` liczy się z bazy (jedno źródło prawdy dla API i wszystkich workerów): etapy potoku (licznik i histogram czasu `radar_stage_duration_seconds`), każde wywołanie LLM (`radar_llm_requests_total` wg dostawcy, celu i wyniku, histogram `radar_llm_latency_seconds`, tokeny, koszt z `RADAR_LLM_PRICES`), kolejki i DLQ z RabbitMQ, wiek ostatniego pobrania i harmonogram źródeł. Alerty (`deploy/observability/alerts.yml`): DLQ > 0, źródło bez pobrania dłużej niż 2× `schedule_s`, błędy i p95 opóźnienia LLM, wolne etapy bez LLM, API niedostępne. Logi to JSON z `raw_id`, `stage`, `source_id`, `duration_ms`.

### Aktualizacja istniejącej instalacji
- Kolejki dostały argument `x-max-priority`: przy aktualizacji usuń stare kolejki `link`, `extract`, `maturity`, `score` w RabbitMQ (albo jego wolumen), inaczej broker odrzuci deklarację (`PRECONDITION_FAILED`).
- Schemat bazy: migracje Alembic (`radar migrate`; w Helm Job post-install/pre-upgrade, API też migruje pod blokadą doradczą Postgresa). Baza utworzona wcześniej przez `create_all` jest najpierw oznaczana jako rewizja `0001`, więc dane zostają.
- `radar reassess` przelicza graf i oceny (też codziennie z beat).

## Dla inwestorów i wykonawców (runda 2)

To od nich zależy, czy pomysł powstanie, więc dostają narzędzia pracy, nie katalog. Wszystko liczone regułami z danych w bazie, bez LLM w czasie zapytania.

| Co | Gdzie | Z czego |
|---|---|---|
| Gotowość inwestycyjna 0–100 | karta pomysłu, `GET /api/cards/{id}` → `investor.readiness` | dojrzałość 35, ochrona IP 20, trakcja 20, zespół 10, ścieżka komercjalizacji 15 (`app/radar/investor.py`) |
| Wycena po dowodach | `investor.adjusted` | szansa wdrożenia rośnie o jawnie wypisane punkty: patent, ≥ 1 mln zł środków publicznych instytucji, spółka/licencja, dorobek zespołu |
| Porównywalne projekty | `investor.comparables` | zrealizowane, finansowane projekty z tego samego sektora (NCBR, Kohesio, CORDIS…), mediana budżetu jako kotwica |
| Memo PDF (inwestor) i specyfikacja wdrożenia (wykonawca) | `GET /api/cards/{id}/memo?kind=inwestor\|wykonawca` → „Zapisz PDF” | wyłącznie pola już policzone przez potok; zero nowych faktów |
| Portfel (lejek transakcji) | `#/portfel` | Nowe → Kontakt → Due diligence → Term sheet → Odrzucone; przeciąganie i klawiatura, notatki, suma wycen |
| Porównanie 2–4 pomysłów | `#/porownaj?ids=…` | najlepsza wartość w wierszu wyróżniona |
| Wdrożenia | `#/wdrozenia`, `GET /api/deployments?side=odbiorca\|wykonawca` | gmina/szkoła/szpital: gotowe rozwiązania + kto wdroży + z czego zapłacić; wykonawca: mapa przychodu w 3 lata per województwo vs. lokalna konkurencja |
| Alerty bez logowania | „Powiadamiaj o nowych” w `#/dopasuj`, `POST /api/watch` → kanał Atom | profil pod anonimowym tokenem, bez e-maila; opcjonalny webhook https (codziennie z beat) |
| API dla partnerów | `/api/v1/ideas`, `/api/v1/match`, `/api/v1/cards/{id}` (OpenAPI: `/docs`) | nagłówek `X-API-Key` (klucze w `RADAR_PARTNER_KEYS`), limit 60 zapytań/min na klucz |

### Publiczny adres i koszt

```powershell
# na VPS (2 vCPU / 4 GB), z RADAR_DOMAIN=radar.twojadomena.pl w .env
docker compose --profile public up -d
```

Caddy (`deploy/public/Caddyfile`) sam pobiera certyfikat HTTPS i ukrywa `/metrics`; kontener `backup` co noc zapisuje zrzut bazy do `./backups`.

**Bez domeny i bez otwartych portów (adres dla jury):** Cloudflare Tunnel przed tym samym API.

```powershell
# .env: RADAR_DEMO_MODE=1, RADAR_LLM_PROVIDERS=mock, RADAR_LOCAL_LLM_URL=http://llm:8080/v1 (bez kluczy chmurowych)
docker compose --profile local-llm --profile tunnel up -d --build
docker compose exec api radar demo        # dane przykładowe + pregeneracja (hasła pisze Bielik na CPU)
docker compose logs cloudflared            # adres https://….trycloudflare.com
```

Szybki tunel nie wymaga konta, ale adres zmienia się po restarcie. Stały adres: tunel nazwany w Cloudflare, `RADAR_TUNNEL_CMD="tunnel --no-autoupdate run"` i `TUNNEL_TOKEN` w `.env` (nigdy w repo). `edge` (`deploy/public/Caddyfile.tunnel`) ukrywa `/metrics` i `/api/basal/train`. Szczegóły i lista kontrolna: [`docs/public-url.md`](docs/public-url.md).

### Koszt LLM: reguły i mały model domyślnie

- Łańcuch dostawców to domyślnie `local,mock`: mały model na CPU, potem reguły. Modele w chmurze (`anthropic`, `openai` na zewnętrznym adresie) są pomijane, dopóki nie ustawisz jawnie `RADAR_LLM_ALLOW_CLOUD=1` (Helm: `config.allowCloud: true`); `/api/config` pokazuje rzeczywisty łańcuch.
- `radar pregenerate` liczy raz i zapisuje w `cards.pregen`: brief do rolek, hasło, wycenę i dopasowanie do odbiorców. Działa po ocenie każdej karty (także przy imporcie partii), po `reassess` i co noc z beat (03:30); przelicza tylko karty, których dane się zmieniły. Endpointy tylko to czytają.
- Hasło pisze Bielik 1.5B (gramatyka GBNF, walidacja, w razie błędu hasło z reguł). Pomiar na 30 rekordach NCBR, 4 vCPU: 2,4 s na nowy rekord; pełnej ekstrakcji z cytatami mały model na CPU nie robi sensownie (27–54 s). Skrypt: `scripts/bench_local_llm.py`.
- Grafana: dashboard „Radar Innowacji — koszty LLM” (`deploy/observability/grafana/dashboards/costs.json`): wywołania wg dostawcy, szacowany koszt, % kart bez dużego LLM (`radar_cards_without_large_llm_ratio`, cel > 90%), stan pregeneracji.

| Pozycja | Miesięcznie |
|---|---|
| VPS 2 vCPU / 4 GB (np. Hetzner CX22, OVH VPS) | ok. 20–35 zł |
| Domena | ok. 5 zł |
| LLM | 0 zł: klasyfikacja Basal, wycena, memo, dopasowanie i alerty działają bez modelu; nowe rekordy może opisywać Bielik 1.5B na CPU (`--profile local-llm`) |
| Razem | **poniżej 50 zł** |

## Harvester danych (`radar/`, `config/`, z gałęzi `feature/pobieranie-danych`)

Osobny pakiet w katalogu głównym: konektory NCBR, Interreg, Biblioteka Nauki, OpenAlex, RAD-on, EPO, CORDIS, FE, UPRP, crawler stron, baza SQLite z historią. W compose działa w profilu `harvester` (`docker compose --profile harvester up`), port `HARVESTER_PORT` (domyślnie 8765). Wyniki (`data/normalized/<id>.jsonl`, w tym `web.jsonl` z crawlera) wchodzą do potoku `app/` przez źródła `harvester-*`; Biblioteka Nauki i RAD-on tylko tą drogą. Rejestr instytucji z RAD-on (`radon_institutions.jsonl`) zasila etap `resolve_org`.

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

**Crawler stron bez LLM** ([`radar/crawl/`](radar/crawl/), witryny w [`config/sites.json`](config/sites.json), opis źródeł: [`docs/zrodla.md`](docs/zrodla.md)): strony uczelni, centrów transferu technologii, klastrów, instytucji finansujących, samorządów i ministerstw → główna treść i metadane → filtr innowacji na słownikach → rekord `radar.record/v1` z kategorią z zadania (`nauka` / `projekty` / `biznes` / `administracja`). Respektuje `robots.txt`, wysyła najwyżej jedno zapytanie na 2 s na host i nie obchodzi zabezpieczeń (taka witryna dostaje status `blocked`).

```bash
python -X utf8 -m radar.crawl --site ur_ctt --max-pages 20 --dry-run   # przegląd: co byłoby rekordem i dlaczego
python -X utf8 -m radar.crawl                                          # witryny, którym minął termin
python -X utf8 -m radar.crawl sites                                    # stan witryn: strony, rekordy, błędy
```

**Odświeżenie wszystkich źródeł jednym poleceniem** ([`radar/refresh.py`](radar/refresh.py), pełna instrukcja: [`docs/odswiezanie-danych.md`](docs/odswiezanie-danych.md)):

```bash
python -X utf8 -m radar.refresh              # wszystkie źródła z rejestru, pobiera tylko to, co nowe
python -X utf8 -m radar.refresh --due-only   # tylko źródła, którym minął termin (tak działa scheduler)
python -X utf8 -m radar.refresh --list       # źródła, kategorie i terminy
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

**Docker** ([`docs/docker.md`](docs/docker.md)): `docker compose up -d --build` uruchamia przeglądarkę na http://localhost:8765 i harmonogram, który co godzinę uruchamia źródła z minionym terminem. Dane trafiają do `./data`, a witryny crawlera są czytane z `./config` (zmiana bez przebudowy obrazu).

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

### Prawdziwe dane (domyślnie)
`docker compose up` pobiera z baz publicznych przez kolejkę i workery (bez syntetyków): **OpenAIRE** `/projects` z polskim partnerem i **Kohesio** projekty spójności UE w Polsce bezpośrednio, a pliki harvestera (`docker compose --profile harvester up` albo `python -X utf8 -m radar.refresh`) przez źródła `harvester-*`: **NCBR**, **Interreg**, **Biblioteka Nauki**, **OpenAlex**, **RAD-on** (NCN, NCBR), **EPO**, **CORDIS**, **FE 2021–2027**, **UPRP** (import) i **crawler stron**. Każde źródło ma harmonogram w `app/sources.yaml`, a przycisk „Pobierz” w zakładce Źródła. `RADAR_DEMO_MODE=1` przełącza na same dane syntetyczne (fallback dla jury bez sieci).

**Dedup** (`dedup`): rekordem kanonicznym klastra jest najpełniejszy (opis, DOI, organizacje, kwoty), a nie pierwszy przetworzony; pełniejszy rekord, który przyjdzie później, przejmuje klaster. Źródła z `group_by_title` (Kohesio) łączą projekty jednego programu o tym samym tytule (np. „Czyste powietrze” w wielu gminach) w jedną grupę z `cluster_size`.

**Rejestr organizacji** (`resolve_org`, T023): instytucje z RAD-on; afiliacje dopasowywane kaskadowo (identyfikator → nazwa i nazwy dawne → skrót → zawieranie → podobieństwo, progi 0,90/0,70). Pewne dopasowanie daje Basalowi typ instytucji, publiczna/prywatna i województwo. `radar orgs match "Wydział Chemiczny Politechniki Rzeszowskiej"` pokazuje dopasowanie.

### Obserwowalność
- `GET /metrics` (Prometheus): etapy potoku, statusy rekordów, źródła (wiek ostatniego pobrania, błędy), decyzje, LLM per dostawca, fallbacki, głębokość kolejek RabbitMQ i DLQ.
- Logi JSON (`RADAR_LOG_FORMAT=json`) z `raw_id`, `stage`, `source_id` w API i workerach.
- `docker compose --profile observability up`: Prometheus (:9090, alerty w `deploy/observability/alerts.yml`), Grafana (:3000, dashboard „Radar Innowacji — potok”), Flower (:5555).

### UI
Neumorfizm (designmd.app/library/neumorphism) w barwach biało-czerwonych z czernią dla kontrastu i beżowym tłem; przełącznik trybu jasny/systemowy/ciemny; logo w stylu ikony aplikacji; układ według szablonu dashboardu Tabler (navbar, nagłówek strony, karty, kafle statystyk); ikony z jednego zestawu (Lucide, `static/icons.svg`); mapa Polski z prawdziwych granic województw (`static/poland.json`, ppatrzyk/polska-geojson, MIT); rolki zbudowane z komponentów (tabliczka lokalizacji, budżet, dojrzałość, ścieżka, odbiorcy).

### Praca w zespole
Zadania dla 3 osób: `.github/issues/` (dane i potok · UI · ocena, LLM, obserwowalność, wdrożenie). Publikacja jako GitHub Issues: `gh auth login`, potem `powershell -ExecutionPolicy Bypass -File scripts/publish-issues.ps1`.
