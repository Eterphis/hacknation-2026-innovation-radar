---
id: T010
title: Deploy, tryb demo, kontrola klucza
status: todo
owner: null
branch: null
depends_on: [T008, T009]
capabilities: [devops]
acceptance:
  - id: AC-1
    run: "docker build -t radar-innowacji ."
    timeout: 1200
  - id: AC-2
    run: "python scripts/smoke.py --url \"$(cat .house/demo-url.txt)\""
    expect: "golden path OK"
    timeout: 300
  - id: AC-3
    run: "env -u ANTHROPIC_API_KEY docker compose run --rm -e ANTHROPIC_API_KEY= -e RADAR_LLM=anthropic app keycheck"
    expect: "mode: demo"
  - id: AC-4
    manual: "Publiczny URL otwarty w oknie incognito na innym urządzeniu i innej sieci; oba przypadki przechodzą; zrzut w .house/reports/T010/."
---
## Objective
The app runs on a public URL the jury can open, from one container, with the key set server-side, and
falls back to a labelled demo mode without a key. `build.md` principle 0 is satisfied.

## Context
- Deploy exactly the image from the T001 `Dockerfile` (no separate build path for the host). Measure and
  record in the report: image size, cold `docker compose up --build` time, warm start time (target < 10 s).
- Build the image for `linux/amd64` and save it as a fallback (`docker save radar-innowacji | gzip >
  radar-innowacji.tar.gz`, kept outside git) so the pitch laptop can run it without network.
- Host: pick the fastest free option that runs a container (Render, Fly.io, Railway); log the choice as
  D-###. The URL goes into `.house/demo-url.txt` (committed; it is public anyway). Key only in the host's
  secret settings.
- `scripts/smoke.py`: `/health`, then UC1 and UC2 through the API, prints `golden path OK`; `--local`
  starts the app in-process.
- Check quota and rate limits of the key; keep a spare key out of the repo.
- Follow `.house/protocols/demo-checklist.md` lines for deploy and keys.

## Out of scope
New features. Custom domain.
