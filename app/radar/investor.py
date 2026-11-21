"""Investor-grade signals for one idea, from data already in the database (no LLM, no network at request time).

An investor or an implementer asks four things before money moves: is it protected (IP), has anyone already paid
for it (traction), who is behind it (team), and what did similar things cost (comparables). Each answer here comes
from records the harvester already collected (NCBR, Kohesio, RAD-on, OpenAIRE, Biblioteka Nauki, CORDIS, patents),
with the record ids it rests on, so every number can be checked. Results feed an investment-readiness score and an
adjusted valuation that states each reason it moved.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from statistics import median

from sqlalchemy import select

from radar.basal.embed import fold
from radar.models import Card, Record

PROJECT_SOURCES = ("kohesio", "ncbr", "cordis", "openaire", "radon", "fe_projects", "interreg")
IP_GRANTED = re.compile(r"(udzielon\w* patent|uzyskan\w* patent|patent nr|patent (?:pl|ep|us)\s?\d|prawo ochronne nr|patented|granted patent)")
IP_FILED = re.compile(r"(zgloszeni\w* patentow|zgloszon\w* do (?:uprp|urzedu patentowego)|wniosek patentow|wzor\w* uzytkow|ochron\w* patentow|patent application|wynalaz)")
SPINOFF = re.compile(r"(spin[- ]?off|spolk\w* celow|spolk\w* spin|start-?up|komercjalizacj\w* przez spolk|licencj\w* udzielon|umow\w* licencyjn)")
_CACHE: dict = {"at": 0.0, "idx": None}
TTL = 600


def _org_key(extra: dict | None, affiliations: list | None) -> str | None:
    ex = extra or {}
    if ex.get("org_id"):
        return f"id:{ex['org_id']}"
    aff = (affiliations or [None])[0]
    return f"name:{re.sub(r'[^a-z0-9]+', ' ', fold(aff))[:80].strip()}" if aff else None


def _amount(amounts: dict | None) -> float:
    return max([v for v in (amounts or {}).values() if isinstance(v, (int, float)) and v > 0] or [0])


def _index(s) -> dict:
    """One pass over all classified records: by organisation, by author, and realized projects per sector."""
    now = time.monotonic()
    if _CACHE["idx"] is not None and now - _CACHE["at"] < TTL:
        return _CACHE["idx"]
    by_org, by_author, realized = defaultdict(list), defaultdict(int), defaultdict(list)
    sector_orgs: dict = defaultdict(dict)
    rows = s.execute(select(Record.id, Record.title, Record.abstract, Record.source_id, Record.kind, Record.year,
                            Record.amounts, Record.affiliations, Record.extra, Record.authors, Record.sector,
                            Record.cost_level, Record.voivodeship, Record.institution_type, Card.id, Card.maturity)
                     .join(Card, Card.record_id == Record.id, isouter=True)
                     .where(Record.status.in_(("extracted", "ready")))).all()
    for (rid, title, abstract, src, kind, year, amounts, affs, extra, authors, sector, cost, woj, itype, cid, mat) in rows:
        amt = _amount(amounts)
        item = {"record_id": rid, "card_id": cid, "title": title, "source_id": src, "kind": kind, "year": year,
                "amount": amt, "text": fold(f"{title} {(abstract or '')[:1500]}"), "voivodeship": woj}
        k = _org_key(extra, affs)
        if k:
            by_org[k].append(item)
            if sector and affs and mat in ("business_ready", "market_ready", "tech_ready"):
                o = sector_orgs[sector].setdefault(k, {"name": str(affs[0])[:120], "voivodeship": woj, "institution_type": itype,
                                                        "ideas": 0, "ready": 0, "funding_pln": 0})
                o["ideas"] += 1
                o["ready"] += mat in ("business_ready", "market_ready")
                o["funding_pln"] += round(amt)
        for a in (authors or [])[:20]:
            name = a.get("name") if isinstance(a, dict) else a
            if name:
                by_author[fold(str(name)).strip()] += 1
        if amt > 0 and sector and (kind in ("project", "solution") or any(p in src for p in PROJECT_SOURCES)) \
                and mat in ("business_ready", "market_ready"):
            realized[sector].append({**item, "cost_level": cost})
    idx = {"by_org": by_org, "by_author": by_author, "realized": realized, "sector_orgs": sector_orgs}
    _CACHE.update(at=now, idx=idx)
    return idx


def implementers(s, sector: str, voivodeship: str | None = None, exclude: str | None = None, n: int = 3) -> list[dict]:
    """Who can deliver in this sector: organisations with ready solutions here, own region first, then by track record."""
    orgs = [o for k, o in _index(s)["sector_orgs"].get(sector or "", {}).items() if k != exclude]
    orgs.sort(key=lambda o: (o["voivodeship"] != voivodeship if voivodeship else 0, -o["ready"], -o["ideas"], -o["funding_pln"]))
    return orgs[:n]


def reset_cache() -> None:
    _CACHE.update(at=0.0, idx=None)


def signals(s, rec: Record, card: Card, bc: dict | None = None) -> dict:
    idx = _index(s)
    text = fold(f"{rec.title} {(rec.abstract or '')[:3000]}")
    org = idx["by_org"].get(_org_key(rec.extra, rec.affiliations) or "", [])
    others = [o for o in org if o["record_id"] != rec.id]

    # --- IP: patents in the organisation's records and patent language in this idea's own text
    org_patents = [o for o in others if o["kind"] == "patent" or "patent" in o["source_id"]]
    granted = bool(IP_GRANTED.search(text)) or rec.kind == "patent"
    filed = bool(IP_FILED.search(text))
    strength = "strong" if granted else "medium" if filed else "weak" if org_patents else "none"
    ip = {"strength": strength, "in_text": "patent udzielony" if granted else "zgłoszenie / wynalazek" if filed else None,
          "org_patents": len(org_patents), "examples": [_ref(o) for o in org_patents[:3]]}

    # --- traction: public money the same organisation already received (projects, grants)
    funded = sorted([o for o in others if o["amount"] > 0], key=lambda o: -o["amount"])
    traction = {"public_funding_pln": round(sum(o["amount"] for o in funded)), "grants": len(funded),
                "last_year": max([o["year"] for o in funded if o["year"]] or [None], key=lambda y: y or 0),
                "own_budget_pln": round(_amount(rec.amounts)) or None, "examples": [_ref(o) for o in funded[:3]],
                "org_records": len(others)}

    # --- team: authors and how much else they have in the corpus
    people = []
    for a in (rec.authors or [])[:12]:
        name = a.get("name") if isinstance(a, dict) else a
        if name:
            people.append({"name": str(name), "records": idx["by_author"].get(fold(str(name)).strip(), 1)})
    people.sort(key=lambda p: -p["records"])
    team = {"people": len(people), "top": people[:3], "prior_records": sum(max(0, p["records"] - 1) for p in people)}

    # --- commercialisation route
    spin = SPINOFF.search(text)
    commercial = {"route": "spółka / licencja wspomniana w opisie" if spin else
                  "firma jako twórca" if rec.institution_type == "firma" else None,
                  "cue": spin.group(0) if spin else None}

    # --- comparables: realized, funded projects in the same sector (cosine on stored embeddings when present)
    comps = [c for c in idx["realized"].get(rec.sector or "", []) if c["record_id"] != rec.id]
    same_cost = [c for c in comps if c.get("cost_level") == rec.cost_level] or comps
    words = set(w for w in re.findall(r"[a-z]{5,}", text))
    scored = sorted(same_cost, key=lambda c: -len(words & set(re.findall(r"[a-z]{5,}", c["text"]))))[:5]
    comparables = {"items": [_ref(c) for c in scored],
                   "median_pln": round(median([c["amount"] for c in scored])) if scored else None,
                   "pool": len(comps)}

    out = {"version": "investor/v1", "ip": ip, "traction": traction, "team": team, "commercial": commercial,
           "comparables": comparables}
    out["readiness"] = readiness(card, out)
    if bc:
        out["adjusted"] = adjust(bc, out)
    return out


def _ref(o: dict) -> dict:
    return {"record_id": o["record_id"], "card_id": o.get("card_id"), "title": (o["title"] or "")[:140],
            "source_id": o["source_id"], "year": o["year"], "amount": round(o["amount"]) or None,
            "voivodeship": o.get("voivodeship")}


MAT_PTS = {"exploring": 8, "tech_ready": 20, "business_ready": 30, "market_ready": 35}
IP_PTS = {"none": 0, "weak": 6, "medium": 14, "strong": 20}


def readiness(card: Card, sig: dict) -> dict:
    """Investment readiness 0-100: maturity 35, IP 20, traction 20, team 10, commercial route 15."""
    t = sig["traction"]
    parts = {
        "dojrzałość": MAT_PTS.get(card.maturity or "exploring", 8),
        "ochrona IP": IP_PTS[sig["ip"]["strength"]],
        "trakcja": min(20, round(4 * (t["grants"] > 0) + 16 * min(1, t["public_funding_pln"] / 20_000_000) + 4 * bool(t["own_budget_pln"]))),
        "zespół": min(10, 3 * (sig["team"]["people"] > 0) + min(7, sig["team"]["prior_records"])),
        "ścieżka komercjalizacji": 15 if sig["commercial"]["route"] else 5 if (card.assessment or {}).get("paths") else 0,
    }
    score = min(100, sum(parts.values()))
    return {"score": score, "parts": parts,
            "label": "gotowe do rozmowy" if score >= 60 else "wymaga due diligence" if score >= 35 else "wczesny etap"}


def adjust(bc: dict, sig: dict) -> dict:
    """Valuation adjusted by evidence: each reason that moved the success probability is listed."""
    p = bc["valuation"]["success_probability"]
    reasons, delta = [], 0.0
    if sig["ip"]["strength"] == "strong":
        delta += .10; reasons.append("+10 pp: patent udzielony")
    elif sig["ip"]["strength"] == "medium":
        delta += .05; reasons.append("+5 pp: zgłoszenie patentowe / wynalazek")
    if sig["traction"]["public_funding_pln"] >= 1_000_000:
        delta += .05; reasons.append("+5 pp: instytucja dostała ≥ 1 mln zł publicznych środków na projekty")
    if sig["commercial"]["route"]:
        delta += .05; reasons.append("+5 pp: istnieje ścieżka komercjalizacji (spółka / licencja / firma)")
    if sig["team"]["prior_records"] >= 3:
        delta += .03; reasons.append("+3 pp: zespół ma inne prace w bazie")
    p2 = min(.95, p + delta)
    base = bc["valuation"]["licence_or_spinoff_pln"]
    value = round(base * p2 / p) if p else base
    anchor = sig["comparables"]["median_pln"]
    return {"success_probability": round(p2, 2), "licence_or_spinoff_pln": min(50_000_000, value), "reasons": reasons,
            "comparable_copy_cost_pln": round(anchor * .3) if anchor else None,
            "note": "mediana budżetów podobnych zrealizowanych projektów × 30% (koszt kopii)" if anchor else None}
