---
id: T009
title: "Frontend: sześć ekranów przepływu"
status: todo
owner: null
branch: null
depends_on: [T001]
capabilities: [typescript, react, ux]
acceptance:
  - id: AC-1
    run: "cd web && npm ci && npm run build"
    timeout: 900
  - id: AC-2
    run: "cd web && npm run lint && npm run typecheck"
  - id: AC-3
    run: "cd web && npm test -- --run"
  - id: AC-5
    run: "docker compose up -d --build && curl -fsS --retry 30 --retry-connrefused --retry-delay 2 http://localhost:8000/ | grep -qi '<div id=\"root\"'; rc=$?; docker compose down; exit $rc"
    timeout: 1200
  - id: AC-4
    manual: "Na danych z fixtures da się przejść oba przypadki z .house/demo-flow.md bez instrukcji; zrzuty 1280×720 i 390×844 w .house/reports/T009/."
---
## Objective
The UI the jury sees: **Radar**, **Zgłoś**, **Karta**, **Ocena** (+ Podobne), **Ścieżka** (+ Dopasowania),
**Panel**, plus **Zgłoś problem** for institutions. Polish, clear, one obvious next action per screen.
Works against a mock API built from contract fixtures until T008 lands, then against the real API.

## Context
- Stack: Vite + React + TypeScript + Tailwind; types generated from `schema/contract.schema.json`
  (`npm run gen:types`); API client in `web/src/api.ts` with a `VITE_API=mock|real` switch; mock data from
  `data/seed` and the expected UC1/UC2 outputs in `.house/demo-flow.md`.
- UX rules that score points (jury criterion „użyteczność i jakość doświadczenia”):
  - a stepper a→e at the top of each innovation (Wykryto/Zgłoszono → Karta → Ocena → Ścieżka → Mierniki);
  - every AI value has a small „AI” badge and a source icon that opens the quoted span; „brak danych” is a
    visible state with an „uzupełnij” action;
  - the assessment shows the rubric level text, not just a number; overrides show both values;
  - „Przykład” label on example data; a banner „Tryb demo (bez klucza AI)” when `/health` says demo;
  - loading states always end; errors in Polish with a retry;
  - readable on a projector (min 16 px body) and on a phone.
- Optional map on Radar (Leaflet, OSM tiles: check licence attribution) only if time allows; a list with
  filters is the baseline.
- Licences of npm packages must be EUPL-compatible (MIT/BSD/Apache/ISC).
- The production build happens inside the Docker `web` stage (T001 Dockerfile) and is served by FastAPI at
  `/`; `npm` on the host is only for development. Keep `package-lock.json` committed so `npm ci` in the
  image is reproducible. Dev: `docker-compose.dev.yml` runs Vite with the API proxied to the `app` service.

## Out of scope
Backend logic, auth, real sending of invitations.
