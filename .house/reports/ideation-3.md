# Ideation round 3: judge scores (after D-006)

- **Judge:** coordinator acting as judge (Opus), 2026-11-21 13:40
- **Requirements (D-006, human):** web app + AI agent. Flow: fetch from external sources (e.g. APIs) → parse → process → score → classify "what for and for whom" → output with a reasoning trace an official (urzędnik) can follow.
- **Input / output (brief §2):** find hidden innovations in schools, universities, local governments and other public institutions, assess potential, show development / transfer / commercialisation / deployment paths. Answer: where and how to search, what information to collect, how to assess potential, how to connect with a user, partner, investor or organisation that needs a similar solution.
- **Still binding:** D-002 (search databases), D-003/D-005 (Helm/K8s, RabbitMQ + Celery, no-skip workers, swappable LLM with fallback). Data facts: `reports/data-access.md`, pipeline: `reports/pipeline-design.md`.
- **Rubric:** `spec.scoring.rubric` (stage I, five criteria, 0-5 each, 20% each, max 25)

Criteria: **C1** Związek z wyzwaniem, **C2** Pomysł i oryginalność, **C3** Użyteczność i UX,
**C4** Kompletność prototypu/demo, **C5** Potencjał wdrożeniowy i transfer.

## What every idea shares (from D-006)
The same backbone: connectors (Biblioteka Nauki, OpenAIRE, RAD-on, Kohesio, EPO Linked Data) → parse → organisation resolution against registers → link and deduplicate → score → classify (what for, for whom) → output. The ideas differ in **what the agent does** and **how the reasoning reaches the official**.

## How each idea answers the brief's four questions

| Question (brief §2) | I-011 | I-012 | I-013 | I-014 | I-015 |
|---|---|---|---|---|---|
| Gdzie i jak szukać | sources + agent tools | agent plans queries per need | nightly scan | as I-011 | sources, rules |
| Jakie informacje zbierać | card fields with evidence | card fields | card fields | card + counter-evidence | fixed checklist |
| Jak oceniać potencjał | rubric + justification | rubric + short reasons | rubric | rubric + for/against | rules and thresholds |
| Jak połączyć z odbiorcą | recipients from catalogue + path | answer to a stated need | push to subscribed institutions | as I-011 | list on the card |

## Scores

| Idea | C1 | C2 | C3 | C4 | C5 | Sum |
|---|---|---|---|---|---|---|
| I-011 Agent-analityk z uzasadnieniem urzędowym | 5 | 4 | 5 | 4 | 4 | **22** |
| I-012 Agent na zlecenie urzędnika | 4 | 3 | 5 | 4 | 4 | **20** |
| I-014 Adwokat i recenzent | 4 | 5 | 4 | 3 | 4 | **20** |
| I-013 Radar ciągły ze skrzynką | 4 | 3 | 4 | 3 | 5 | **19** |
| I-015 Karta-checklista | 4 | 2 | 4 | 5 | 4 | **19** |

## Justification per criterion

**I-011 Agent-analityk z uzasadnieniem urzędowym**
- C1 5: covers the full flow of D-006 and all four questions of §2; scenario a-e maps one to one.
- C2 4: agents with citations exist (Elicit, Perplexity); a justification in the structure of an administrative decision, with links to public records, does not.
- C3 5: an official reads a format they already know; every claim is one click from its source.
- C4 4: one agent with 4-5 tools and a capped number of calls per record is buildable in the time left.
- C5 4: the same format works for any institution type; agent tools are swappable connectors.

**I-012 Agent na zlecenie urzędnika**
- C1 4: strong on "how to connect with someone who needs it"; detection only on demand.
- C2 3: "chat that searches" is a common pattern.
- C3 5: the simplest entry for an official.
- C4 4: one query, a visible plan, a shortlist: crisp demo.
- C5 4: useful anywhere.

**I-013 Radar ciągły ze skrzynką rekomendacji**
- C1 4: systematic detection plus delivery to recipients.
- C2 3: alerts are a known pattern.
- C3 4: no effort for the official, but less control.
- C4 3: needs institution profiles and time to show value; feedback learning will not show within 24 h.
- C5 5: the most "after the hackathon" of all: a running service for many institutions.

**I-014 Adwokat i recenzent**
- C1 4: strong on "how to assess potential".
- C2 5: for/against with evidence, then a verdict, is new for this domain and answers "AI overrates everything".
- C3 4: pros and cons are easy to read; longer output.
- C4 3: two to three LLM passes per record: cost, latency, more to validate.
- C5 4: mirrors the two-reviewer practice of public grant evaluation.

**I-015 Karta-checklista**
- C1 4: answers all questions, briefly.
- C2 2: a scorecard; weak on "agent AI" from D-006.
- C3 4: predictable, printable.
- C4 5: lowest risk.
- C5 4: easy to adopt.

## Recommendation
**A) I-011 as the core + I-012 as the entry + one reviewer pass from I-014, output in the I-015 card layout.**
- Background pipeline finds and prepares candidates (D-002). The agent studies each candidate with tools and writes the justification.
- The official can also start from a need (I-012): the agent plans queries and reuses the same pipeline.
- One extra "reviewer" pass looks for weaknesses (missing evidence, duplicate, existing solution) before the verdict; shown as "Co przemawia przeciw".
- The result page is the one-page card with traffic lights per criterion, the justification and the links.
- Estimated: C1 5, C2 5, C3 5, C4 4, C5 4 = **23/25**. C4 risk: keep the agent's tool calls capped and the reviewer to a single pass.

**B) I-011 alone** (22/25): lowest risk, no chat entry, no counter-arguments.

**C) I-012 + I-011 without the reviewer** (about 22/25): best demo opener, keeps the overrating risk.

## Agent design (applies to A)
- **Tools** (each a typed function over our store or a connector, results cached): `search_sources(query, sources)`, `get_record(id)`, `lookup_registry(name|id)`, `find_similar(record_id)`, `find_duplicates(record_id)`, `list_recipients(filters)`.
- **Duplicate check (D-007):** a `dedup` stage runs before the LLM (same record again, same object across sources by DOI / patent application / project code, near-duplicates, semantic duplicates) and after extraction (similar solutions in other institutions = possible duplicated work). The agent reads the result; it never merges records itself. Design: `reports/pipeline-design.md` section 16.
- **Limits:** at most 8 tool calls and 2 LLM retries per record; on reaching the limit the record goes to `needs_review` with the reason, never silently dropped (D-005).
- **Deterministic stages stay in code:** parsing, registry matching, public status, maturity level, recipient candidates. The agent explains and decides among candidates; it does not invent facts.
- **Swappable LLM with offline fallback (D-003):** the reasoning trace records which provider produced it; offline mode shows rule-based reasons for the demo set.

## Reasoning trace for the official (format proposal)

```
UZASADNIENIE REKOMENDACJI                                   Radar Innowacji · karta nr 0412

1. Co ustalono (fakty i dowody)
   • Politechnika Rzeszowska (uczelnia publiczna, woj. podkarpackie)  [RAD-on]
   • opracowała metodę X, opis: „…”                                    [Biblioteka Nauki, art. 5104]
   • zgłosiła ją do ochrony patentowej w 2013 r., patent udzielony 2016  [EPO, EP 2886569]
   • brak śladu wdrożenia poza uczelnią                                 [Kohesio, RAD-on: nie znaleziono]
   • duplikaty: ten sam artykuł w BN i OpenAIRE (DOI) połączono;
     EP A1 i B1 to jedno zgłoszenie; podobne rozwiązanie: brak          [etap dedup]

2. Według jakich kryteriów oceniono
   dojrzałość · przenaszalność · skala problemu · koszt wdrożenia · dowody

3. Ocena
   dojrzałość ●●●○○ gotowa technologia (jest patent, brak wdrożenia)
   przenaszalność ●●●●○ … (uzasadnienie, cytat)
   …

4. Co przemawia przeciw
   • brak danych o kosztach wdrożenia
   • podobne rozwiązanie wdrożono w … (jeśli znalezione)

5. Rozstrzygnięcie: do czego i dla kogo
   ścieżka: licencja albo pilotaż w JST
   odbiorcy: Gmina A (powód…), Szpital B (powód…)
   mierniki: liczba pilotaży w 12 mies., …

6. Ograniczenia
   ocena wstępna; kwoty z OpenAIRE niepełne; patenty krajowe (UPRP) niedostępne automatycznie
```

The example's facts are an illustration of the format, not verified claims about a real innovation.

## Cheapest point to gain
C2 and C3 together: show the same card twice, once as a raw LLM answer and once as the structured justification with links; the difference is the pitch.
