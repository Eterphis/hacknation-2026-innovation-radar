# Prior art: I-002 Public-source scout (automatic detection)

- **Researcher:** coordinator (web search), 2026-11-21

## Closest existing
1. **ITONICS** (commercial, live): AI technology scouting over a curated data lake and the web, ranked against a company roadmap. Corporate, tech-only. https://www.itonics-innovation.com/blog/ai-technology-scouting
2. **Valuer.ai** (Copenhagen, live): AI matchmaking of corporates and investors with startups, ~250 companies added daily (self-reported). Startups only. https://tech.eu/profiles/27244/copenhagen-based-valuer-ai-identifies-some-of-europes-medtech-startups-to-watch/
3. **StartUs Insights** (live): AI discovery engine over 1.3M+ startups. https://www.startus-insights.com/innovators-guide/ai-driven-innovation-scouting/
4. **Linknovate** (live): detects emerging technologies and the organisations behind them from publications, grants and patents.
5. **EU Innovation Radar** (see I-001): detection via project reviews, not crawling.

## What is genuinely different
Scouting aimed at public institutions and non-commercial innovations (school registers of pedagogical innovations, BIP resolutions, Interreg/NCBR project lists), where commercial scouting tools do not look.

## Market signal
Corporate innovation scouting is a funded market; no public-sector equivalent found. Polish schools publish innovation registers on their own sites and BIP as scattered PDFs, which is exactly "hidden".

## Risk for the rubric
Low novelty risk. High execution risk: scraping heterogeneous PDFs and BIP pages in 24 h, licence questions for crawled data (regulamin §4 ust. 8), and a live crawl can fail in the demo. Mitigation: recorded crawl over a fixed set of sources plus a live re-run of one source.
