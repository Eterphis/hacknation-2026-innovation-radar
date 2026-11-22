# Kubernetes: skalowanie i obserwowalność

## Jak się skaluje

Każdy etap potoku ma własną kolejkę RabbitMQ, a workery są osobnymi Deploymentami (`values.yaml → workers`). Skaluje się to, co jest wąskim gardłem, bez ruszania reszty.

| Element | Jak skalować | Domyślnie |
|---|---|---|
| API (FastAPI, bezstanowe) | `api.autoscaling.enabled=true` → HPA po CPU (2–6 podów); PodDisruptionBudget trzyma ≥ 1 pod przy drenowaniu węzła | 2 repliki |
| Workery ingest (pobieranie, normalizacja, Basal) | **KEDA** (`keda.enabled=true`): ScaledObject na długość kolejek RabbitMQ (`messagesPerReplica: 50`, 1–8 podów); bez KEDA: `workers[].autoscaling.enabled=true` → HPA po CPU | 1 replika, 4 procesy |
| Workery LLM (karta, dojrzałość, ocena) | jak wyżej, osobno; przy małym modelu dokładamy repliki `localLLM` (llama.cpp, CPU) | 1 replika, 2 procesy |
| Mały model (Bielik 1.5B) | `localLLM.replicas` | 1, 2 vCPU / 3–4 GB |
| Postgres / RabbitMQ | StatefulSety w chartcie dla demo; na produkcji usługi zarządzane (`postgresql.enabled=false`, `externalDatabase.url`) | 1 |

Gwarancje przy skalowaniu w górę i w dół:
- `acks_late` + `reject_on_worker_lost`: zabity pod oddaje zadanie do kolejki;
- `terminationGracePeriodSeconds: 600`: worker kończy bieżące zadania przed zamknięciem;
- idempotencja po `(raw_id, etap, hash treści)`: zadanie dostarczone dwa razy nie robi nic złego;
- DLQ łapie zadania, które padły po ponowieniach;
- migracje robi jeden Job Helma (blokada advisory w Postgresie).

```powershell
# autoskalowanie po kolejkach (KEDA zainstalowana w klastrze)
helm upgrade --install radar deploy/helm/innovation-radar --set keda.enabled=true --set api.autoscaling.enabled=true
```

CI (GitHub Actions) stawia chart na k3d i czeka, aż wszystkie pody będą Ready; `helm lint` i `promtool` sprawdzają chart i reguły alertów.

## Co widać (obserwowalność)

- **Metryki** (`/metrics`, Prometheus; `serviceMonitor.enabled=true` dla Prometheus Operatora): uruchomienia i czasy etapów (`radar_stage_runs_total`, `radar_stage_duration_seconds`), rekordy wg statusu i źródła, kolejki (`radar_queue_messages`, `radar_queue_unacked`, `radar_queue_consumers`), DLQ, świeżość i błędy źródeł, wywołania LLM (liczba, opóźnienie, tokeny, koszt, fallbacki), średni wynik kart, decyzje i polubienia.
- **Dashboard Grafany** (`deploy/observability/grafana/dashboards/radar.json`, 22 panele): rekordy, etapy, przepustowość, p95 etapów, kolejki, DLQ, LLM wg dostawcy, opóźnienie p50/p95, koszt, świeżość źródeł, workery i zadania Celery (Flower).
- **Alerty** (`deploy/observability/alerts.yml`): `RadarDeadLetters`, `RadarSourceFailed`, `RadarSourceStale`, `RadarLLMErrors`, `RadarLLMSlow`, `RadarStageSlow`, `RadarQueueBacklog`, `RadarApiDown`.
- **Logi JSON** z polami `source_id`, `stage`, `raw_id`, `provider`, gotowe pod Loki/ELK.
- **Zdrowie:** `/healthz` (proces), `/readyz` (baza + broker); workery: `celery inspect ping` w sondach k8s i w healthcheckach compose.
- **Test dymny całego wdrożenia:** `python scripts/smoke.py https://adres`: 25 sprawdzeń, w tym zgłoszenie aż do ocenionej karty.

Lokalnie: `docker compose --profile observability up -d`, a potem Grafana na `:3000` i Flower na `:5555`.
