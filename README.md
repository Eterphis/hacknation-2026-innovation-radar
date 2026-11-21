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

## Aplikacja (`app/`, `deploy/helm/`)

Python 3.12: FastAPI (API + UI operatora), Celery + RabbitMQ (jedna kolejka na etap, `acks_late`, DLQ, idempotencja po `(raw_id, stage, content_hash)`), Postgres, router LLM z fallbackiem (`anthropic → openai-compatible → mock`).

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
`values.yaml`: `workers[]` (grupy kolejek i współbieżność), `sources:` (treść sources.yaml → ConfigMap; źródła push dostają konsumentów), `secrets:` / `existingSecret`, `postgresql.enabled` / `rabbitmq.enabled` (wbudowane albo zewnętrzne), `ingress`, `api.autoscaling`.

Zadania do zrobienia: [`.house/tasks/`](.house/tasks/) (T020–T036).

### Główne flow (szczegóły: [`.house/reports/main-flow.md`](.house/reports/main-flow.md))

1. **Wejście danych:** pull/push/formularz, jak wyżej.
2. **Basal** (`app/radar/basal/`, bez LLM, milisekundy na rekord, zwykły vCPU): jedna decyzja *przyjmij / do przeglądu / odrzuć* z powodem oraz etykiety na 7 osiach (sektor PKD, obszar technologii, typ innowacji, typ instytucji, dojrzałość, koszt, województwo) i priorytet w kolejce (`x-max-priority`). Słowniki + podobieństwo do prototypów etykiet w przestrzeni embeddingów + głowa decyzji uczona na decyzjach operatora (`POST /api/basal/train`).
3. **Agent wdrożeniowy** (`app/radar/pipeline/assess.py`): narzędzia (podobne pomysły z grafu, kontekst regionu, odbiorcy) → ścieżki „kto co robi”, ryzyka z mitygacjami, odbiorcy, 6 jawnych kryteriów z wagami, mierniki skuteczności → Basal sprawdza spójność → wynik 0–100 do rankingu. Bez klucza działa wersja regułowa; z LLM (chmura albo lokalny model) agent dopisuje uzasadnienia na faktach z narzędzi.
4. **Prezentacja** (UI w stylu „Zero Interface”): *Przegląd* (trendy, wyróżniające się, najbardziej zaawansowane, gotowe do powielenia, tanie wdrożenia, wymagające dużego budżetu, ukryte perełki, dublowanie prac, luki regionalne, portfel koszt × dojrzałość), *Odkrywaj* (fasety), *Graf* (jak w Obsidianie), *Mapa* (kartogram + macierz województwo × sektor), *Rolki* (jednostronicowe briefy z polubieniami), *Zgłoś* (podgląd Basala na żywo), *Operator*. Wyszukiwanie klawiszem `/`, także głosem tam, gdzie przeglądarka wspiera Web Speech API.

### Lekki model na VPS (bez GPU)

```bash
RADAR_LOCAL_LLM_URL=http://llm:8080/v1 docker compose --profile local-llm up --build
```
llama.cpp server z **Bielik 1.5B v3.0 Instruct GGUF Q8_0** (polski, Apache-2.0, ~1,7 GB, pobierany przy pierwszym starcie). W Helm: `--set localLLM.enabled=true`. Embeddingi: domyślnie `hashing` (numpy, zero pobierań); `RADAR_EMBEDDER=fastembed` = `multilingual-e5-small` na ONNX/CPU (`pip install .[embed]`).

### Aktualizacja istniejącej instalacji
- Kolejki dostały argument `x-max-priority`: przy aktualizacji usuń stare kolejki `link`, `extract`, `maturity`, `score` w RabbitMQ (albo jego wolumen), inaczej broker odrzuci deklarację (`PRECONDITION_FAILED`).
- Schemat bazy rozszerzony (Basal, embeddingi, krawędzie, polubienia); do czasu migracji Alembic (T030) nowa baza albo `radar initdb` na pustej.
- `radar reassess` przelicza graf i oceny (też codziennie z beat).
