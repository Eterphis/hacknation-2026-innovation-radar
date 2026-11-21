---
title: "[Ocena + Ops] Agent wdrożeniowy z narzędziami, lokalny LLM, ewaluacja, obserwowalność i wdrożenie"
labels: [ocena, ops, priorytet-1]
assignee_role: "Osoba C: ocena, LLM, obserwowalność, wdrożenie"
---
## Cel
Ocena pomysłów jest wiarygodna i mierzalna, działa na lekkim modelu na CPU, a system da się obserwować i wdrożyć na Kubernetes.

## Zakres
1. **Agent `analyze` (T027)**
   - Pętla tool-calling: `find_similar`, `regional_context`, `recipients`, `lookup_registry`.
   - Działa na routerze LLM: `local` (Bielik 1.5B/4.5B GGUF), potem chmura, na końcu reguły.
   - Recenzent „co przemawia przeciw” i brief.
   - Każde twierdzenie ma cytat lub link do rekordu, a kod to sprawdza (`app/radar/pipeline/assess.py`).
2. **Basal (T021, T038)**
   - Embeddingi `multilingual-e5-small` (fastembed, ONNX, CPU) wbudowane w obraz, ze skalibrowanymi progami.
   - Zbiór testowy 60 rekordów (sektor, decyzja, typ instytucji), wynik w `.house/experiments.csv`.
3. **Obserwowalność**
   - `/metrics` (Prometheus): czasy etapów, koszt i opóźnienie LLM per dostawca, fallbacki, DLQ.
   - Dashboard Grafany w repo (provisioning).
   - Alerty: DLQ > 0, źródło bez pobrania dłużej niż 2× harmonogram, błędy LLM.
   - Flower dla Celery.
   - Logi JSON z `raw_id`, `stage` i `source_id`.
4. **Wdrożenie (T031, T032)**
   - CI: pytest obu pakietów, build obrazu, `helm lint` i `helm template`, push do GHCR.
   - Instalacja na k3d według README.
   - Publiczny URL dla jury.
   - Sekrety przez `existingSecret`.
5. **Migracje (T030):** Alembic zamiast `create_all`.

## Kryteria akceptacji
- [ ] Na zbiorze testowym trafność sektora wynosi co najmniej 0,8, a decyzji Basala co najmniej 0,85 (zapis w `.house/experiments.csv`).
- [ ] `docker compose --profile observability up` pokazuje dashboard z licznikami etapów, kolejkami i LLM.
- [ ] CI jest zielone, a po `helm install` na k3d wszystkie pody są Ready.

## Pliki
`app/radar/pipeline/assess.py`, `app/radar/llm/*`, `app/radar/basal/*`, `app/radar/observability.py`, `deploy/`, `.github/workflows/`. Nie ruszać konektorów (Osoba A) ani `static/` (Osoba B).
