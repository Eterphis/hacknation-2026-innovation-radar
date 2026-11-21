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
