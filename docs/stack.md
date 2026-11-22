# Stos technologiczny i modele (stan na 22.11.2026)

## W skrócie
Radar sam zbiera publiczne dane o innowacjach, klasyfikuje je bez LLM (Basal), ocenia regułami i opcjonalnie małym modelem, a potem pokazuje je inwestorom, samorządom, uczelniom, szkołom, startupom i innowatorom z wyceną i ścieżką wdrożenia. Koszt działania: poniżej 50 zł/mies. na VPS, bez dużego modelu.

| Warstwa | Technologia | Po co |
|---|---|---|
| Harvester (`radar/`) | Python 3.12, `httpx`, crawler, `refresh.py`, scheduler w Dockerze | pobiera NCBR, Kohesio, RAD-on, OpenAIRE, Biblioteka Nauki, CORDIS, OpenAlex, UPRP; zapisuje `data/normalized/*.jsonl` |
| Ingest | konektory `rest`, `graphql`, `oaipmh`, `sparql`, `snapshot` (pull) i `webhook`, `amqp`, `gcp_pubsub`, `kafka` (push); mapowanie JMESPath w `app/sources.yaml` | jedno wejście `ingest()` dla każdego źródła |
| Kolejka | RabbitMQ + Celery: kolejka na etap (`harvest → normalize → resolve_org → dedup → gate → link → extract → maturity → score`), `acks_late`, DLQ, priorytety, idempotencja `(raw_id, stage, content_hash)` | odporność i skalowanie workerów |
| Baza | PostgreSQL 16, SQLAlchemy 2, migracje Alembic (`0001`–`0004`); SQLite w testach | rekordy, karty, organizacje, polubienia, listy obserwowanych |
| API | FastAPI: `/api/*` (UI), `/api/v1/*` (partnerzy, klucz + limit), `/metrics` | jedna aplikacja, OpenAPI pod `/docs` |
| UI | vanilla JS SPA (bez frameworka), neumorfizm biało-czerwony na beżu, ikony Lucide, mapa z `polska-geojson` (MIT) | szybkie, bez buildu; trasy `#/…` |
| Obserwowalność | Prometheus + Grafana (dashboard), alerty, Flower, logi JSON | profil compose `observability` |
| Wdrożenie | Docker Compose (profile: `harvester`, `observability`, `local-llm`, `public` z Caddy HTTPS i backupem), Helm chart (k3d w CI), GitHub Actions | od laptopa do klastra |
| Grafiki | Higgsfield (`z_image`), statyczne WebP w `static/` | tła grup, sektorów, banery; zero kosztu w runtime |

## Modele
| Model | Gdzie | Rola | Koszt |
|---|---|---|---|
| **Basal** (własny) | `app/radar/basal/` | klasyfikator wieloosiowy bez LLM: sektor, obszar technologii, typ innowacji, instytucja, województwo, koszt; słowniki + prototypy + wyuczona głowa decyzyjna (zapisywana w bazie, trenowana z decyzji operatora) | mikrosekundy na rekord, CPU |
| Embeddingi: hashing (`stem6 + char4`, 512 wymiarów) | domyślnie | podobieństwo, dedup, graf, klastry „Podobne metody” | 0 |
| Embeddingi: `intfloat/multilingual-e5-small` (384 wym., ONNX przez fastembed) | `RADAR_EMBEDDER=fastembed` | lepsze podobieństwo dla polskiego i angielskiego | CPU, ~120 MB |
| **Bielik 1.5B v3.0 Instruct** (GGUF Q8_0, llama.cpp) | profil `local-llm` / Helm `localLLM.enabled` | ekstrakcja karty i agent oceny dla nowych rekordów na CPU | 0 zł (VPS) |
| Claude Sonnet 5.5 (`claude-sonnet-5-5`) | `RADAR_ANTHROPIC_API_KEY` | opcjonalny mocniejszy model w routerze | za token |
| OpenAI-compatible (`gpt-4o-mini` domyślnie) | `RADAR_OPENAI_*` | opcjonalny fallback | za token |
| Reguły (`mock`, `heuristic-v1`) | zawsze | ostatni fallback: aplikacja działa bez żadnego klucza | 0 |

Router LLM: `local → anthropic → openai → reguły` (z timeoutami i walidacją cytatów: każde pole karty musi mieć cytat ze źródła).

## Co jest liczone regułami (bez LLM)
Wycena i business case (`business.py`: TAM/SAM/SOM z GUS, licencja, tantiemy, zwrot, programy), sygnały inwestorskie (`investor.py`: IP, trakcja, zespół, porównywalne, gotowość 0–100), dopasowanie profilu (`/api/match`), wdrożenia, klastry, memo PDF, alerty.
