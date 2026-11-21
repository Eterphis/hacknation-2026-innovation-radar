# hacknation-2026-innovation-radar

HackNation 2026 (Bydgoszcz, 21–22.11.2026): **Radar Innowacji**, the task from Podkarpackie Centrum Innowacji.

Shared contest state lives in [`.house/`](.house/): spec, tasks, decisions, questions, progress.

## Setup

This repo is a contest of the AI Software House toolkit, which is vendored in our main repo
([Eterphis/hacknation-2026-odwolania2json](https://github.com/Eterphis/hacknation-2026-odwolania2json)).
Follow that repo's `TEAM.md` first, then fetch this repo into it:

```bash
cd hacknation-2026-odwolania2json
python3 house/bin/house sync                      # clones this repo into house/contests/radar-innowacji
python3 house/bin/house adapt radar-innowacji     # your agents, skills and hooks (per machine, gitignored)
cd house/contests/radar-innowacji && claude       # then /house-start with the full task text
```

On Windows use `py -3.12 house\bin\house …` instead of `python3 house/bin/house …`.
