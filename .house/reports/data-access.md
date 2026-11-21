# Data access: databases from the brief (§7) and close substitutes

- **Researcher:** coordinator (web search), 2026-11-21 12:10
- **Why:** D-002 makes ingest from these databases the core of the product. Each source needs a way in that works
  for the jury too (build.md principle 0). Nothing below was called yet: every "live" source needs one real,
  cheap call before it goes into a task.

| Source (brief §7) | Way in | Key / account | Verdict for the demo |
|---|---|---|---|
| UPRP e-Wyszukiwarka (patents PL) | `api.uprp.gov.pl` webservice (OpenAPI 3.0 per WIPO catalogue), endpoint `/ewyszukiwarka/api/external/search-bibliographics-results`; newer `api2` uses IP allow-listing | token or IP allow-list, unclear | **uncertain**: try one call; fallback = snapshot of search results exported by hand |
| EPO Register | Open Patent Services (OPS) REST, free up to 4 GB/week | **free registration required** (human creates account) | **live** if a key is ready by 18:00, else snapshot |
| PBN | API JSON, read needs an application key issued to integrators by OPI | app key via OPI, not in 24 h | **no**: use Biblioteka Nauki / OpenAIRE for publications instead |
| PPM (ppm.edu.pl) | web UI only found | — | snapshot or skip |
| Biblioteki cyfrowe PAN (czasopisma.pan.pl, dLibra) | dLibra exposes OAI-PMH (`/dlibra/oai-pmh-repository.xml`, endpoint for czasopisma.pan.pl unconfirmed) | none | **live, probably**: check `?verb=Identify` |
| Biblioteka Nauki (PAN journals, substitute) | documented OAI-PMH `https://bibliotekanauki.pl/api/oai/articles` | none | **live** (best open publication source) |
| BazTOL (PUT) | old web app | — | snapshot or skip |
| Interreg (interreg.gov.pl lista projektów) | web list; keep.eu has API (key by e-mail, case by case) and **CSV/Excel export from the site** | API key: no; export: none | **snapshot** from keep.eu export, refreshed by hand |
| NCBR wyszukiwarka sukcesów | web pages | none | **snapshot** (small scrape of the list) |
| Kohesio (EU cohesion projects, substitute) | portal aggregating operation lists; 2021-2027 incomplete | none | snapshot; API not verified |

## Consequences for the design
1. **Connector per source + one normalised record** (title, abstract, authors, affiliation, institution type, year, source, link, licence). Live connectors where open (Biblioteka Nauki OAI-PMH, dLibra OAI-PMH, EPO OPS with key, UPRP if the call works), snapshot connectors (CSV/JSON) for the rest. Same code path, the snapshot is just another connector.
2. **Demo mode** = snapshots only, so the jury's run never depends on our keys.
3. **Licence of harvested data** (regulamin §4 ust. 8): keep harvested records out of the EUPL code repo or ship only a small sample with source attribution; ask mentors (Q-004).
4. **Accounts are the human's**: EPO OPS registration (and any UPRP token) must be created by the team, not by an agent.

## Sources
- https://www.epo.org/en/searching-for-patents/data/web-services/ops , https://epo.org/en/service-support/ordering/fair-use
- https://polon.nauka.gov.pl/pomoc/wp-content/uploads/2019/11/prezentacja_api_pbn.pdf
- https://doc.bibliotekanauki.pl/en/oai-pmh-api-documentation/
- https://confluence.wipo.int/confluence/spaces/ATR/pages/1640995272/CWS+ATR+PI+2024+PL
- https://keep.eu/faq/api-how-to-access-keep_eu-data-in-open-data-format/
- https://kohesio.ec.europa.eu/pl/informacje

## Checked with real calls (2026-11-21 13:22)

Raw responses (not committed): scratchpad `api/` folder of the coordinator session.

| Question | Call | Result |
|---|---|---|
| Biblioteka Nauki: formats, ORCID, DOI | `?verb=ListMetadataFormats`, `ListRecords` (`oai_dc`, `oai_openaire`, `jats`, from=2026-10-01) | 200. Formats: `oai_dc`, `oai_openaire`, `jats`, `bwmeta`. 20 records per page, `resumptionToken` works. **ORCID: 0 of 20** records in `oai_openaire` and `jats`. **DOI: 11 of 20** (`alternateIdentifier type=DOI`). Affiliation: free text per author (`datacite:affiliation`, JATS `<aff>`), no ID, no type. Funding: none. Rights per record: 12/20 "Wszystkie prawa zastrzeżone", 5/20 CC BY-NC-ND 3.0 PL, 3/20 CC BY 4.0. `datestamp` reflects metadata changes (2017 articles stamped 2026-10-22). |
| OpenAIRE `/organizations` fields | `?search=Politechnika Rzeszowska`, `?countryCode=PL` | 200. Fields: `legalName`, `legalShortName`, `alternativeNames[]` (incl. Polish name), `websiteUrl`, `country`, `pids[]` (**ROR, Wikidata, ISNI, PIC, GRID, OrgReg, FundRef**). **No organisation type, no city or region.** 5,284 organisations with country PL. |
| OpenAIRE coverage of Polish national funders | `/projects?fundingShortName=NCN` / `NCBR` (control: `EC` 131,872, `NSF` 601,434) | **NCN: 0, NCBR: 0.** Polish national grants are not in OpenAIRE under these names. PRz has 38 projects, EC-funded. |
| Kohesio beneficiaries and identifiers | `/api/projects` (list), `/api/beneficiaries?name=…`; detail, Linked Data and SPARQL tried | List: 200 (fields as in the team note). **`/api/beneficiaries` works**: `label`, `budget`, `euBudget`, `cofinancingRate`, `numberProjects`, Linked Data id and **Wikidata link** (PRz → Q3578303, the same as OpenAIRE's Wikidata pid). **No NIP/REGON in the API.** Project detail endpoint not found (400/404); linkedopendata.eu entity and SPARQL: **403** from this machine. CSV per country exists (`PL-latest.csv` on the data page) with an optional `Beneficiary_Unique_Identifier` (VAT or registration number, often empty per Kohesio FAQ), but the direct file URL was not found (redirects to home). |
| RAD-on (POL-on) open data | `/opendata/polon/institutions`, `/projects`, `/patents` | Institutions 200: **`regon`, `nip`, `krs`, `iKindName` (e.g. "Uczelnia niepubliczna"), `uTypeName`, `voivodeship`, `city`, `addresses`, `status`**. Projects 200: **Polish national projects (e.g. NCN)** with `financingInstitutions`, `implementingInstitutions` (uuid, name, leader), `projectAbstractPl/En`, `keywords`, `disciplines`, dates, `totalFunds`. Filter by institution name was ignored (same first result). **Patents endpoint: 404** (`polon/patents` and variants). |
| RSPO API | `https://api-rspo.men.gov.pl/api/placowki/` | **no connection** (curl 000); `rspo.gov.pl` site answers 200. Host or path to confirm. |
| KRS API | `/api/krs/OdpisAktualny/0000019193` | 200 but HTML "Przerwa techniczna" (maintenance at the time). Retry later. |

### What changes
- **ORCID is not a usable join key** for Biblioteka Nauki; join on DOI (about half of records), then title + year + author.
- **Wikidata id is a join key between OpenAIRE organisations and Kohesio beneficiaries** (both expose it). ROR is in OpenAIRE.
- **RAD-on fills two gaps:** institution type, public/private, REGON/NIP/KRS and voivodeship for universities and institutes; Polish national projects that OpenAIRE lacks (NCN seen in the sample; NCBR coverage not yet checked).
- **Kohesio beneficiary IDs:** only via CSV (optional, often empty); otherwise match by name + Wikidata.
- **Patents:** still no source verified (UPRP/EPO OPS untested, RAD-on has none).
- **Biblioteka Nauki rights:** most records must be processed from metadata only (title, abstract, keywords), not the PDF.

## Patents and NCBR, checked with real calls (2026-11-21 13:27)

| Question | Call | Result |
|---|---|---|
| UPRP e-Wyszukiwarka | `ewyszukiwarka.pue.uprp.gov.pl/search/simple-search` and `/api/external/…` | **Blocked by bot protection (Incapsula)** for automated clients. Not bypassed. |
| UPRP external API | `api.uprp.gov.pl` (portal "PUEUP API Zewnętrzne"), `/ewyszukiwarka/api/external/search-bibliographics-results` | **401 "Full authentication is required"**. Needs an account or token from UPRP; not obtainable by an agent. |
| EPO OPS without key | `ops.epo.org/3.2/rest-services/published-data/search` | **403** (fair use: registration required). |
| **EPO Linked Data (SPARQL)** | `https://data.epo.org/linked-data/query` | **200, no key.** Applicant search by name works (`vcard:fn`), e.g. "Politechnika Rzeszowska im. Ignacego Lukasiewicza": **17 EP publications**. Publication: number, kind (A1/B1…), date, title, language, `applicantVC`, `inventorVC`, `agentVC`. Application: filing date, **grant date**, **CPC classes**, patent family. |
| **EPO document XML** | `data.epo.org/linked-data/representation/publication/EP/<nr>/<kind>.xml` (also .html, .pdf) | **200, no key**: `<abstract>`, `<description>`, claims (7 in the sample). |
| NCBR projects in RAD-on | `/opendata/polon/projects` with filters | **NCBR projects are present** (e.g. hydrogen catalyst and hydrogen storage projects financed by NCBR). Total **48,853 projects**, paged by `token`. Filter `projectTitlePl` works (193 for "wodór"); **filters by financing or implementing institution are ignored**, so filter after download. |

### What changes
- **EP patents: live source without a key** (EPO Linked Data + document XML), applicant matched by name to the organisation registry. Gives the `tech_ready` evidence and patent text for the LLM.
- **Polish national patents (PL, UPRP): no automated source.** Options: a manual export from e-Wyszukiwarka by a team member as a snapshot, or applying for UPRP API access (not within 24 h). State as a limitation.
- **RAD-on projects:** one full download (about 49k records) per refresh, filtered locally by institution and funder (NCN, NCBR).
