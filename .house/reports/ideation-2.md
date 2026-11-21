# Ideation round 2: judge scores (after D-002)

- **Judge:** coordinator acting as judge (Opus), 2026-11-21 12:20
- **Constraint (D-002, mentors):** the system itself searches databases (e.g. those in brief §7) for ideas and processes them further.
- **Rubric:** `spec.scoring.rubric` (stage I, five criteria, 0-5 each, 20% each, max 25)
- **Inputs:** `ideas.md` I-006..I-010, `reports/prior-art-I-006..010.md`, `reports/data-access.md`, round 1 (`reports/ideation-1.md`)
- **Time left:** about 22.5 h; golden path due 18:00 today

Criteria: **C1** Związek z wyzwaniem, **C2** Pomysł i oryginalność, **C3** Użyteczność i UX,
**C4** Kompletność prototypu/demo, **C5** Potencjał wdrożeniowy i transfer.

## What D-002 changes from round 1
- Step a of the demo becomes "automatic detection from the databases"; a manual form is at most an extra.
- I-002 (scout) was round 1's riskiest idea; with the brief's own databases and OAI-PMH / CSV exports the risk is smaller than crawling BIP pages (`reports/data-access.md`).
- I-004 (transfer passport) stays valid as the output stage of any round 2 idea.

## Scores

| Idea | C1 | C2 | C3 | C4 | C5 | Sum | Data risk |
|---|---|---|---|---|---|---|---|
| I-009 Sprawdzone gdzie indziej, wdrożone tutaj | 4 | 4 | 4 | 4 | 5 | **21** | low (keep.eu CSV) |
| I-006 Lejek radaru | 5 | 3 | 4 | 4 | 4 | **20** | medium (several connectors) |
| I-010 Zapytaj radar | 4 | 3 | 5 | 4 | 4 | **20** | medium |
| I-007 Łańcuch dowodów | 4 | 5 | 3 | 3 | 4 | **19** | high (entity linking) |
| I-008 Uśpione patenty uczelni | 3 | 3 | 4 | 4 | 3 | **17** | medium (EPO key, UPRP unclear) |

## Justification per criterion

**I-006 Lejek radaru**
- C1 5: does exactly what mentors asked and maps onto a-e (detect → organise → score → recipients → justification).
- C2 3: a scouting funnel is expected; EU Innovation Radar and OpenAIRE exist.
- C3 4: operator (PCI) gets a ranked feed; institutions get cards.
- C4 4: feasible with 2 live + 2 snapshot connectors.
- C5 4: adding a source is a new connector; repeatable scoring.

**I-007 Łańcuch dowodów**
- C1 4: strong on "how to assess potential" with transparent criteria (brief §5).
- C2 5: maturity and "hiddenness" derived from linked records is not what EU Innovation Radar, Lens or Dimensions do.
- C3 3: powerful but needs explaining.
- C4 3: entity resolution across Polish sources is the hardest part in 24 h.
- C5 4: the evidence makes scores auditable, which public institutions need.

**I-008 Uśpione patenty uczelni**
- C1 3: technological only; brief stresses non-technological innovations too.
- C2 3: tech-transfer offices and EEN already list offers.
- C3 4: clear for universities and PCI.
- C4 4: a small patent set is easy to demo.
- C5 3: one institution type.

**I-009 Sprawdzone gdzie indziej, wdrożone tutaj**
- C1 4: strong on transfer and pathway; "hidden" is reframed as "known in a database, unknown where needed".
- C2 4: Interreg good practices are curated by hand; automatic fit ranking per institution is new.
- C3 4: an institution sees "these 5 projects fit you, here is how".
- C4 4: project data comes from CSV exports, no key.
- C5 5: directly brief §9 and the purpose of Interreg; non-technological innovations included.

**I-010 Zapytaj radar**
- C1 4: covers similar-solution search and matching; detection only on demand.
- C2 3: "AI search box" is a common pattern.
- C3 5: the simplest possible entry for a teacher or clerk.
- C4 4: one query across sources is a crisp demo.
- C5 4: useful in any institution.

## Recommendation
**A) I-006 funnel as the backbone + I-007 "light" for scoring + I-004/I-009 transfer output.**
Connectors (Biblioteka Nauki or dLibra OAI-PMH live, Interreg/NCBR snapshot, EPO OPS live if a key is ready) → one record → public-institution filter and innovation type → **maturity from evidence** (simple links only: same institution + similar text across paper / patent / project, with visible confidence) → duplicate groups → pathway, recipients and transfer passport → expected metrics.
Estimated: C1 5, C2 5, C3 4, C4 3, C5 5 = 22/25. C4 is the risk; keep I-007 to simple matching.

**B) I-009 alone** (projects only, transfer focus): lowest data risk, 21/25, but drops patents and publications.

**C) I-006 + I-010** (funnel plus "ask the radar" entry): strongest UX and simplest demo, about 21/25, novelty stays at 3.

## Cheapest point to gain
C2: show one innovation whose maturity badge links to its paper, patent and (missing) deployment project; that single screen answers "this exists" (EU Innovation Radar uses questionnaires).

## Architecture (D-003, applies to every option)
Added 2026-11-21 12:22 at the human's request: Helm on Kubernetes, workers that never skip a record, RabbitMQ + Celery, swappable LLM API with fallback.

**Pipeline as queues** (one Celery queue per stage, RabbitMQ broker):
`harvest` (one task per source and page) → `normalize` → `classify` (public-institution filter, innovation type) → `link` (evidence chain, duplicates) → `score` → `route` (pathway, recipients, transfer passport). Each stage writes its result to the store and enqueues the next stage for that record.

**No-skip guarantees ("zabezpieczenie przed pominięciem"):**
- `acks_late=True`, `task_reject_on_worker_lost=True`, `prefetch_multiplier=1`: a record whose worker dies goes back to the queue.
- Idempotent tasks keyed by `(source, record_id, stage)`: a retried or duplicated message does not create a second card.
- Retries with exponential backoff for network and LLM errors; after the last retry the message goes to a dead-letter queue, never silently dropped.
- Reconciliation job: per source and stage, `harvested = processed + in_flight + dead_lettered`; any gap is shown on the operator screen and re-enqueued.
- Meaning check on LLM output: the extracted card is validated against a schema (required fields, non-empty summary, institution type, source quote that supports each field); a card that fails is retried with the validation errors, then marked `needs_review` instead of passing as complete. (Interpretation of "pominięcie sensu"; confirm in Q-006.)

**Swappable LLM with fallback:**
- One adapter interface (`extract`, `classify`, `score_explain`, `embed`), provider chosen by config/env; primary + secondary provider, with a circuit breaker that switches on errors or timeouts.
- Last fallback is offline: rules and keyword scoring plus cached LLM results for the demo set, so the jury's run works without any key (build.md principle 0). Every card shows which provider produced it.

**Kubernetes / Helm:**
- One chart: `api`, `web`, `worker` (Deployment per queue, scalable replicas), `beat` (scheduled harvests), RabbitMQ and the database as dependencies or values for external services; secrets for LLM keys, none in the image.
- For the jury: the same images run with `docker compose up` (or k3d/kind with `helm install`), demo mode on by default.

**Effect on the scores:** ranking unchanged (it applies to all ideas). C5 gains evidence for "skalowanie na wiele organizacji" and "integracja z istniejącymi systemami" (worker replicas, adapters). C4 risk grows: about 3 h of infrastructure work before the golden path; mitigate by building on docker compose first and adding the Helm chart as its own task in parallel.
