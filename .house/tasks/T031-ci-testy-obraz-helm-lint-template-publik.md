---
id: T031
title: "CI: testy, obraz, helm lint/template, publikacja do GHCR"
status: todo
owner: null
branch: null
depends_on: []
capabilities: []
acceptance:
  - id: AC-1
    run: "test -f .github/workflows/ci.yml"
    timeout: 600
  - id: AC-3
    manual: "zielony przebieg CI na PR; obraz ghcr.io/eterphis/innovation-radar:<sha> opublikowany z main"
protected:
  - app/tests/test_pipeline.py
---
## Objective
GitHub Actions: pytest, `docker build app`, `helm lint` i `helm template` z wartościami włączającymi konsumenta push i ingress, push obrazu do GHCR z main (tag = sha i latest).

## Context
`app/Dockerfile`, `deploy/helm/innovation-radar`, `docker-compose.yml`. Lokalnie sprawdzone: helm lint OK, template renderuje 15 obiektów.

## Out of scope
Wdrożenie na klaster (T032).
