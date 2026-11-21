# Ideation round 1: judge scores

- **Judge:** coordinator acting as judge (Opus), 2026-11-21
- **Rubric:** `spec.scoring.rubric` (stage I, five criteria, 0-5 each, 20% each, max 25)
- **Inputs:** `ideas.md` I-001..I-005, `reports/prior-art-I-00*.md`, brief §3, §5, §6, §9
- **Time left at scoring:** about 23 h; golden path due 18:00 today

Criteria: **C1** Związek z wyzwaniem, **C2** Pomysł i oryginalność, **C3** Użyteczność i UX,
**C4** Kompletność prototypu/demo, **C5** Potencjał wdrożeniowy i transfer.

## Scores

| Idea | C1 | C2 | C3 | C4 | C5 | Sum | Demo by 18:00? |
|---|---|---|---|---|---|---|---|
| I-004 Paszport transferu | 4 | 4 | 4 | 4 | 5 | **21** | yes, needs I-001 card as input |
| I-003 Giełda problem ↔ rozwiązanie | 4 | 4 | 4 | 3 | 4 | **19** | yes with seeded both sides |
| I-001 Radar z jawną oceną | 5 | 2 | 4 | 4 | 3 | **18** | yes, simplest |
| I-002 Zwiadowca źródeł | 3 | 4 | 3 | 2 | 4 | **16** | risky (scraping) |
| I-005 Wywiad + mapa | 3 | 2 | 4 | 3 | 3 | **15** | yes |

## Justification per criterion

**I-001 Radar z jawną oceną**
- C1 5: maps one-to-one onto demo scenario a-e (brief §6).
- C2 2: EU Innovation Radar (same name), OPSI and MC Baza innowacji publicznych exist; a juror from an innovation centre likely knows them.
- C3 4: one flow for any institution type; quality depends on the form.
- C4 4: fully buildable in 24 h with seeded data and an LLM.
- C5 3: catalogue plus score; the "what happens next" (brief §9) is thin on its own.

**I-002 Zwiadowca źródeł publicznych**
- C1 3: answers "gdzie i jak szukać" and step a, not c-e by itself.
- C2 4: nobody scouts public, non-R&D sources (prior-art card).
- C3 3: useful for an operator (PCI), not for the teacher or clerk.
- C4 2: heterogeneous BIP pages and PDFs, licence questions (regulamin §4 ust. 8), live crawl can fail.
- C5 4: repeatable, scales by adding sources.

**I-003 Giełda problem ↔ rozwiązanie**
- C1 4: covers similar search, de-duplication and matching (three of six desired mechanisms).
- C2 4: public ↔ public matching is new; IN-PART and GovTech Inno Lab are adjacent, not the same.
- C3 4: clear value for both sides.
- C4 3: a two-sided exchange needs believable seed data on both sides.
- C5 4: network effect across many institutions.

**I-004 Paszport transferu**
- C1 4: strongest answer to "ścieżka transferu / wdrożenia" and steps d-e; needs a card from I-001 as input.
- C2 4: "Innowacje w samorządzie" proves the format, but its 30 packages are hand-written; generating them for any innovation plus ranking adopters is new.
- C3 4: an institution gets a concrete "how to do it here" document.
- C4 4: package generation and fit ranking over a seeded list of institutions is feasible.
- C5 5: directly the brief's §9 ("co dzieje się z innowacją po jej zidentyfikowaniu", use in real institutions).

**I-005 Wywiad 5-minutowy + mapa**
- C1 3: only steps a-b.
- C2 2: chat intake and dashboards are expected features.
- C3 4: lowest effort for a teacher or clerk.
- C4 3: easy to build, little to show beyond the input.
- C5 3: generic.

## Recommendation
Build **I-001 as the backbone** (it is the demo scenario a-e and the jury's checklist) with **I-004 as the differentiator** for the pitch:
submission → card → transparent score (rubric built on EU Innovation Radar maturity levels and OPSI's four dimensions, cited, which answers the novelty risk) → similar solutions → **transfer passport + ranked adopters + expected metrics**.
Estimated combined score: C1 5, C2 4, C3 4, C4 4, C5 5 = 22/25.
**Stretch, in order:** I-003 "institutions report problems" (reuses the similarity engine), then I-002 on one fixed source as "automatic detection" for step a.
Park I-005 as the input layer (a conversational form) only if time allows.

## Cheapest point to gain
C2: name and cite EU Innovation Radar and OPSI on a slide and show the step they lack (adoption package + adopters).
