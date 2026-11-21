# Prior art: I-007 Evidence chain (cross-source linking)

- **Researcher:** coordinator, 2026-11-21 (items marked * are from general knowledge, not re-checked today)

## Closest existing
1. **Lens.org*** (live): links patents to the scholarly works they cite; strongest existing match for the linking itself.
2. **Dimensions*** (Digital Science, commercial): links grants, publications, patents and clinical trials per researcher and institution.
3. **OpenAIRE Graph*** (EU, live): links publications to funded projects.
4. **EU Innovation Radar** (live): maturity from expert questionnaires, not from linked records. https://innovation-radar.ec.europa.eu/methodology

## What is genuinely different
Uses the links to decide maturity and "hiddenness" transparently: every step of the score points at a record (paper, patent, project) the reviewer can open. "Hidden" gets an operational definition: a result with a patent or paper but no deployment project.

## Market signal
Dimensions is a paid product for research offices; tech-transfer offices manually do this tracing.

## Risk for the rubric
Low to medium novelty risk (linking exists, scoring from links for public-sector innovation does not). High execution risk: entity resolution across Polish sources (name spellings, affiliations) in 24 h; mitigate with a small curated demo set and simple matching (normalised author + affiliation + embedding similarity) with a visible confidence.
