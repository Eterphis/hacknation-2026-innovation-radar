"""Business insights over the scored collection — every answer is a list with its rule, so the UI can say why.

hot trends · standouts · most advanced · ready to copy (practically realised) · need big budget · cheap wins ·
hidden gems · duplication risk · regional gaps · portfolio (cost x maturity)
"""

from __future__ import annotations

from collections import Counter, defaultdict

from fastapi import APIRouter
from sqlalchemy import select

from radar.basal import taxonomy as T
from radar.basal.classifier import label_pl
from radar.db import session
from radar.models import Card, Edge, Record

router = APIRouter(prefix="/api")
LEVELS = ["exploring", "tech_ready", "business_ready", "market_ready"]
COSTS = ["niski", "sredni", "wysoki", "bardzo_wysoki"]


def _row(r: Record) -> dict:
    c = r.card
    sc = (c.assessment or {}).get("scores", {})
    g = lambda k: (sc.get(k) or {}).get("score")  # noqa: E731
    amount = max([v for v in (r.amounts or {}).values() if isinstance(v, (int, float))] or [0]) or None
    return {
        "card_id": c.id, "title": c.solution_name or r.title, "institution": ", ".join((r.affiliations or [])[:1]),
        "voivodeship": r.voivodeship, "sector": r.sector, "sector_pl": label_pl("sector", r.sector),
        "tech_area": r.tech_area, "tech_pl": label_pl("tech_area", r.tech_area),
        "innovation_type": r.innovation_type, "institution_type": r.institution_type,
        "maturity": c.maturity, "maturity_i": LEVELS.index(c.maturity) if c.maturity in LEVELS else 0,
        "cost": r.cost_level, "cost_i": COSTS.index(r.cost_level) if r.cost_level in COSTS else 1,
        "cost_pl": label_pl("cost_level", r.cost_level), "amount": amount,
        "score": c.score or 0, "likes": c.likes or 0, "hidden": c.hidden, "decision": c.decision,
        "novelty": g("nowosc"), "transfer": g("przenaszalnosc"), "evidence": g("sila_dowodow"),
        "path": ((c.assessment or {}).get("paths") or [{}])[0].get("path"),
        "synthetic": bool((r.extra or {}).get("synthetic")), "year": r.year,
    }


def _top(rows, key, n=6, cond=lambda x: True):
    return sorted([x for x in rows if cond(x)], key=key)[:n]


@router.get("/insights")
def insights():
    with session() as s:
        recs = s.scalars(select(Record).join(Card, Card.record_id == Record.id)
                         .where(Record.status == "ready", Card.decision != "rejected", Card.score.is_not(None))).all()
        rows = [_row(r) for r in recs]
        by_id = {r.id: r for r in recs}
        edges = s.scalars(select(Edge).where(Edge.weight >= 0.3).order_by(Edge.weight.desc()).limit(50)).all()
        dup = []
        for e in edges:
            a, b = by_id.get(e.src_id), by_id.get(e.dst_id)
            if not a or not b or not a.card or not b.card:
                continue
            ia, ib = (a.affiliations or [""])[0], (b.affiliations or [""])[0]
            if ia.split(",")[0].strip().lower() == ib.split(",")[0].strip().lower():
                continue
            dup.append({"a": {"card_id": a.card.id, "title": a.card.solution_name or a.title, "institution": ia, "voivodeship": a.voivodeship},
                        "b": {"card_id": b.card.id, "title": b.card.solution_name or b.title, "institution": ib, "voivodeship": b.voivodeship},
                        "similarity": round(e.weight, 2)})
            if len(dup) >= 5:
                break

    if not rows:
        return {"empty": True}

    # ---- hot trends: technology areas weighted by volume, community interest and quality
    groups = defaultdict(list)
    for x in rows:
        if x["tech_area"]:
            groups[x["tech_area"]].append(x)
    max_n = max(len(v) for v in groups.values())
    max_l = max([sum(i["likes"] for i in v) for v in groups.values()] + [1])
    trends = []
    for k, v in groups.items():
        n, likes, avg = len(v), sum(i["likes"] for i in v), sum(i["score"] for i in v) / len(v)
        regions = len({i["voivodeship"] for i in v if i["voivodeship"]})
        heat = 0.45 * n / max_n + 0.25 * likes / max_l + 0.2 * avg / 100 + 0.1 * min(regions, 5) / 5
        trends.append({"key": k, "pl": label_pl("tech_area", k), "ideas": n, "likes": likes, "avg_score": round(avg, 1),
                       "regions": regions, "heat": round(heat * 100), "ready": sum(1 for i in v if i["maturity_i"] >= 2)})
    trends.sort(key=lambda t: -t["heat"])

    nontech = sum(1 for x in rows if x["innovation_type"] not in (None, "technologiczna"))
    insts = {x["institution"].split(",")[0].strip().lower() for x in rows if x["institution"]}
    portfolio = [{k: x[k] for k in ("card_id", "title", "maturity_i", "cost_i", "score", "sector", "sector_pl", "voivodeship", "likes")} for x in rows]

    # ---- regional gaps: sectors present nationally but absent in a region
    sec_v = defaultdict(Counter)
    for x in rows:
        if x["sector"] and x["voivodeship"]:
            sec_v[x["sector"]][x["voivodeship"]] += 1
    gaps = []
    for sec, cnt in sec_v.items():
        total = sum(cnt.values())
        if total < 2:
            continue
        missing = [v for v in T.VOIVODESHIPS.values() if cnt.get(v, 0) == 0]
        gaps.append({"sector": sec, "pl": label_pl("sector", sec), "ideas": total, "regions_with": len(cnt),
                     "missing": missing, "source_regions": [v for v, _ in cnt.most_common(2)]})
    gaps.sort(key=lambda g: (-g["ideas"], len(g["missing"])))

    def need_budget(x):
        return x["cost_i"] >= 2 and x["maturity_i"] <= 2

    # Discovery lists exclude cards already highlighted above them, so each answers its own question.
    used: set[int] = set()

    def pick(key, cond, n=6, exclusive=True):
        out = _top(rows, key, n, lambda x: cond(x) and not (exclusive and x["card_id"] in used))
        used.update(x["card_id"] for x in out)
        return out

    standouts = pick(lambda x: (-(x["novelty"] or 0), -x["score"]), lambda x: x["score"] >= 70 and (x["novelty"] or 0) >= 4, 5)
    realized = pick(lambda x: (-x["maturity_i"], -(x["transfer"] or 0), -x["score"]), lambda x: x["maturity_i"] >= 2 and (x["transfer"] or 0) >= 4)
    cheap = pick(lambda x: (x["cost_i"], -(x["transfer"] or 0), -x["score"]), lambda x: x["cost_i"] <= 1 and x["maturity_i"] >= 1 and x["score"] >= 70)
    hidden = pick(lambda x: (-x["score"], x["likes"]), lambda x: 1 <= x["maturity_i"] <= 2 and x["likes"] <= 1
                  and x["institution_type"] in ("szkola", "uczelnia", "instytut"))

    return {
        "kpi": {
            "ideas": len(rows), "institutions": len(insts),
            "voivodeships": len({x["voivodeship"] for x in rows if x["voivodeship"]}),
            "avg_score": round(sum(x["score"] for x in rows) / len(rows), 1),
            "nontech_share": round(100 * nontech / len(rows)),
            "ready_to_copy": sum(1 for x in rows if x["maturity_i"] >= 2 and (x["transfer"] or 0) >= 4),
            "need_budget": sum(1 for x in rows if need_budget(x)),
            "cheap_wins": sum(1 for x in rows if x["cost_i"] <= 1 and x["maturity_i"] >= 1 and x["score"] >= 70),
            "budget_needed_pln": sum(x["amount"] or 0 for x in rows if need_budget(x)),
            "synthetic_share": round(100 * sum(1 for x in rows if x["synthetic"]) / len(rows)),
        },
        "rules": {
            "trends": "obszar technologii: 45% liczba pomysłów, 25% polubienia, 20% średnia ocena, 10% rozproszenie po województwach",
            "standouts": "wynik ≥ 70 i nowość ≥ 4/5 (brak bliskich odpowiedników w bazie); kolejne listy pomijają już pokazane karty",
            "advanced": "najwyższa dojrzałość, potem siła dowodów",
            "realized": "gotowe do wdrożenia lub na rynku i przenaszalność ≥ 4/5 — działa u twórcy, można powielać",
            "budget": "koszt wysoki lub bardzo wysoki, dojrzałość co najwyżej „gotowe do wdrożenia” — bez finansowania nie ruszy",
            "cheap": "koszt niski lub średni, co najmniej prototyp, wynik ≥ 70 — szybkie wdrożenie przy małym budżecie",
            "hidden": "szkoły, uczelnie i instytuty: prototyp lub działające wdrożenie u twórcy, mało polubień, jeszcze niewidoczne",
            "duplicates": "podobieństwo treści ≥ 0,30 między różnymi instytucjami — kandydaci do współpracy zamiast dublowania",
            "gaps": "sektor obecny w danych, ale bez pomysłów w województwie — tam warto przenieść rozwiązania",
        },
        "trends": trends[:8],
        "standouts": standouts,
        "advanced": _top(rows, lambda x: (-x["maturity_i"], -(x["evidence"] or 0), -x["score"])),
        "realized": realized,
        "budget": _top(rows, lambda x: (-(x["amount"] or 0), -x["cost_i"], -x["score"]), cond=need_budget),
        "cheap": cheap,
        "hidden": hidden,
        "duplicates": dup,
        "gaps": gaps[:6],
        "portfolio": portfolio,
    }
