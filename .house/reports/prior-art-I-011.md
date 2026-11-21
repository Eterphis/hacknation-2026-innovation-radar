# Prior art: I-011 Analyst agent with an official-style justification

- **Researcher:** coordinator, 2026-11-21 (items marked * are from general knowledge, not re-checked today)

## Closest existing
1. **Elicit*** and **Consensus*** (live): research agents that answer with citations to papers; for researchers, not for officials, and they do not route to adopters.
2. **Perplexity*** (live): cited answers from the web; general purpose.
3. **EU Innovation Radar** (live): maturity and market potential per innovation, from expert questionnaires, without a reasoning trace. https://innovation-radar.ec.europa.eu/methodology
4. **Kodeks postępowania administracyjnego, art. 107 § 3*** (format, not a product): a decision's justification contains the facts found, the evidence, and the legal basis. Every Polish official knows this structure.

## What is genuinely different
The reasoning trace is written in the structure an official already reads every day (findings with evidence → criteria → assessment → decision → limits), and every finding links to a record the official can open. The agent's tools are the task's own databases and public registers.

## Market signal
Explainability and accountability are required for AI used in public administration (EU AI Act transparency duties*); the brief asks for transparent criteria (§5).

## Risk for the rubric
Low novelty risk for the format; medium for "agent with citations" in general. Defence: the KPA-style justification and routing to concrete institutions. Execution risk: agent loops and cost; cap tool calls per record and keep deterministic stages in code.
