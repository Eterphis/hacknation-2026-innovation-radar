---
id: T032
title: "Wdrożenie Helm na k3d i publiczny URL dla jury"
status: todo
owner: null
branch: null
depends_on: [T031]
capabilities: []
acceptance:
  - id: AC-1
    manual: "helm install na k3d: wszystkie pody Ready, Job migracji zakończony, źródła demo pobrane z UI"
  - id: AC-2
    manual: "publiczny URL otwarty z czystej przeglądarki na innym urządzeniu; tryb demo widoczny bez kluczy"
protected:
  - app/tests/test_pipeline.py
---
## Objective
Chart `deploy/helm/innovation-radar` zainstalowany na k3d według README z values dla demo; publiczny URL, jeśli starczy czasu (D-005: compose to ścieżka dla jury).

## Context
D-003, D-005, `.house/playbooks/build.md` zasada 0, `deploy/helm/innovation-radar/values.yaml`.

## Out of scope
Produkcyjny Postgres/RabbitMQ (zostają wbudowane StatefulSety).
