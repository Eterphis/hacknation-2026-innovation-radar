"""Exploration API: filter + facets, Obsidian-like graph, regions (map + matrix + gaps), reels feed with likes,
and live Basal classification for the submission form."""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select

from radar.basal import taxonomy as T
from radar.basal.classifier import city, classify, label_pl, train_head
from radar.basal.graph import build_graph
from radar.db import session
from radar.models import Card, Like, Record

router = APIRouter(prefix="/api")
AXES = ("sector", "tech_area", "innovation_type", "institution_type", "voivodeship", "cost_level")


def _filters(q=None, sector=None, tech_area=None, innovation_type=None, institution_type=None, voivodeship=None,
             maturity=None, cost_level=None, min_score=None, decision=None, exclude: str | None = None):
    from radar.sources.registry import hidden_source_ids

    cond = [Record.status.in_(("extracted", "ready"))]
    hidden = hidden_source_ids()
    if hidden:
        cond.append(Record.source_id.not_in(hidden))
    for axis, val in (("sector", sector), ("tech_area", tech_area), ("innovation_type", innovation_type),
                      ("institution_type", institution_type), ("voivodeship", voivodeship), ("cost_level", cost_level)):
        if val and axis != exclude:
            cond.append(getattr(Record, axis).in_(val.split(",")))
    if maturity and exclude != "maturity":
        cond.append(Card.maturity.in_(maturity.split(",")))
    if min_score is not None:
        cond.append(Card.score >= min_score)
    if decision:
        cond.append(Card.decision.in_(decision.split(",")))
    if q:
        like = f"%{q}%"
        cond.append(or_(Record.title.ilike(like), Record.abstract.ilike(like), Card.solution_name.ilike(like)))
    return and_(*cond)


def idea_dict(r: Record) -> dict:
    c = r.card
    return {
        "card_id": c.id, "record_id": r.id, "title": c.solution_name or r.title, "summary": c.summary_pl,
        "source_id": r.source_id, "synthetic": bool((r.extra or {}).get("synthetic")),
        "institution": ", ".join((r.affiliations or [])[:2]), "year": r.year,
        "labels": {a: {"value": getattr(r, a), "pl": label_pl(a, getattr(r, a)) if a != "voivodeship" else getattr(r, a)} for a in AXES},
        "maturity": c.maturity, "score": c.score, "priority": r.priority, "likes": c.likes, "decision": c.decision,
        "path": ((c.assessment or {}).get("paths") or [{}])[0].get("path"),
        # plate data for components (location, budget, institution)
        "city": city(*(r.affiliations or []), r.abstract, voivodeship=r.voivodeship), "voivodeship": r.voivodeship, "sector": r.sector,
        "tech_area": r.tech_area, "institution_type": r.institution_type, "cost_level": r.cost_level,
        "cost_range": T.COST_RANGE.get(r.cost_level or ""),
        "amount": max([v for v in (r.amounts or {}).values() if isinstance(v, (int, float))] or [0]) or None,
    }


SORTS = {"score": Card.score.desc(), "priority": Record.priority.desc(), "likes": Card.likes.desc(), "newest": Card.id.desc()}


@router.get("/ideas")
def ideas(q: str | None = None, sector: str | None = None, tech_area: str | None = None, innovation_type: str | None = None,
          institution_type: str | None = None, voivodeship: str | None = None, maturity: str | None = None,
          cost_level: str | None = None, min_score: float | None = None, decision: str | None = None,
          sort: str = "score", limit: int = 100, offset: int = 0):
    f = dict(q=q, sector=sector, tech_area=tech_area, innovation_type=innovation_type, institution_type=institution_type,
             voivodeship=voivodeship, maturity=maturity, cost_level=cost_level, min_score=min_score, decision=decision)
    with session() as s:
        base = select(Record).join(Card, Card.record_id == Record.id).where(_filters(**f))
        total = s.scalar(select(func.count()).select_from(base.subquery()))
        rows = s.scalars(base.order_by(SORTS.get(sort, SORTS["score"]).nulls_last()).limit(min(limit, 500)).offset(offset)).all()
        items = [idea_dict(r) for r in rows]
        facets = {}
        for axis in AXES + ("maturity",):
            col = Card.maturity if axis == "maturity" else getattr(Record, axis)
            cnt = s.execute(select(col, func.count()).select_from(Record).join(Card, Card.record_id == Record.id)
                            .where(_filters(**f, exclude=axis)).group_by(col)).all()
            facets[axis] = [{"value": v, "pl": (label_pl(axis, v) if axis not in ("voivodeship", "maturity") else v), "count": n}
                            for v, n in sorted(cnt, key=lambda kv: -kv[1]) if v]
    return {"total": total, "items": items, "facets": facets}


@router.get("/graph")
def graph(q: str | None = None, sector: str | None = None, tech_area: str | None = None, innovation_type: str | None = None,
          institution_type: str | None = None, voivodeship: str | None = None, maturity: str | None = None,
          hubs: str = "sector,tech_area,voivodeship", limit: int = 300):
    f = dict(q=q, sector=sector, tech_area=tech_area, innovation_type=innovation_type, institution_type=institution_type,
             voivodeship=voivodeship, maturity=maturity)
    with session() as s:
        recs = s.scalars(select(Record).join(Card, Card.record_id == Record.id).where(_filters(**f))
                         .order_by(Card.score.desc().nulls_last()).limit(min(limit, 1000))).all()
        return build_graph(s, recs, tuple(h for h in hubs.split(",") if h in AXES))


@router.get("/regions")
def regions(sector: str | None = None, tech_area: str | None = None):
    """Per voivodeship: ideas (all / in the selected sector), share vs national, and the voivodeship x sector matrix.
    gap > 0 = the region has fewer ideas in the sector than the national average per region (transfer opportunity,
    or an under-developed sector locally)."""
    with session() as s:
        rows = s.execute(select(Record.voivodeship, Record.sector, Record.tech_area, func.count())
                         .join(Card, Card.record_id == Record.id).where(_filters())
                         .group_by(Record.voivodeship, Record.sector, Record.tech_area)).all()
    all_v = list(T.VOIVODESHIPS.values())
    total_v, sel_v, matrix = Counter(), Counter(), defaultdict(Counter)
    for v, sec, tech, n in rows:
        if not v:
            continue
        total_v[v] += n
        matrix[v][sec] += n
        if (not sector or sec == sector) and (not tech_area or tech == tech_area):
            sel_v[v] += n
    avg = sum(sel_v.values()) / len(all_v)
    out = []
    for v in all_v:
        out.append({"voivodeship": v, "ideas": total_v.get(v, 0), "selected": sel_v.get(v, 0),
                    "gap": round(avg - sel_v.get(v, 0), 2),
                    "top_sectors": [{"sector": k, "pl": label_pl("sector", k), "count": c} for k, c in matrix[v].most_common(3) if k]})
    sectors = [{"key": k, "pl": d["pl"]} for k, d in T.SECTORS.items()]
    return {"national_avg": round(avg, 2), "regions": out, "sectors": sectors,
            "matrix": {v: dict(matrix[v]) for v in all_v}}


@router.get("/feed")
def feed(offset: int = 0, limit: int = 10, sector: str | None = None, voivodeship: str | None = None):
    """Reels: one-page briefs, approved first, then pending (rejected never). Ranking: score + likes."""
    with session() as s:
        q = (select(Record).join(Card, Card.record_id == Record.id)
             .where(_filters(sector=sector, voivodeship=voivodeship), Card.decision != "rejected", Card.brief.is_not(None))
             .order_by((Card.decision == "approved").desc(), (Card.score + 2 * Card.likes).desc().nulls_last(), Card.id)
             .limit(min(limit, 50)).offset(offset))
        out = []
        for r in s.scalars(q):
            d = idea_dict(r)
            d["brief"] = r.card.brief
            out.append(d)
        return out


def _voter(x_voter: str | None) -> str:
    if not x_voter or len(x_voter) < 8:
        raise HTTPException(400, "brak identyfikatora głosującego (X-Voter)")
    return hashlib.sha256(x_voter.encode()).hexdigest()[:32]  # never store the raw browser id


@router.post("/cards/{card_id}/like")
def like(card_id: int, x_voter: str | None = Header(default=None)):
    v = _voter(x_voter)
    with session() as s:
        c = s.get(Card, card_id)
        if c is None:
            raise HTTPException(404)
        existing = s.scalar(select(Like).where(Like.card_id == card_id, Like.voter == v))
        if existing:
            s.delete(existing)
            liked = False
        else:
            s.add(Like(card_id=card_id, voter=v))
            liked = True
        s.flush()
        c.likes = s.scalar(select(func.count()).select_from(Like).where(Like.card_id == card_id))
        return {"card_id": card_id, "liked": liked, "likes": c.likes}


@router.get("/labels")
def labels():
    return {"sector": {k: v["pl"] for k, v in T.SECTORS.items()},
            "tech_area": {k: v["pl"] for k, v in T.TECH_AREAS.items()},
            "innovation_type": {k: v["pl"] for k, v in T.INNOVATION_TYPES.items()},
            "institution_type": {k: v["pl"] for k, v in T.INSTITUTION_TYPES.items()} | {"unknown": "nieustalony"},
            "cost_level": T.COST_PL, "voivodeship": list(T.VOIVODESHIPS.values()),
            "maturity": {"exploring": "badania", "tech_ready": "technologia gotowa", "business_ready": "gotowe do wdrożenia", "market_ready": "na rynku"}}


class ClassifyIn(BaseModel):
    title: str
    description: str
    institution: str | None = None
    institution_type: str | None = None
    region: str | None = None


@router.post("/basal/classify")
def basal_classify(x: ClassifyIn):
    """Live preview for the submission form: what Basal will decide, before anything is stored."""
    b = classify(title=x.title, abstract=x.description, affiliations=[x.institution] if x.institution else [],
                 region=x.region, kind="solution", declared_institution=x.institution_type, min_chars=80)
    b.pop("features", None)
    return b


@router.post("/basal/train")
def basal_train():
    """Train Basal's decision head on operator decisions (approved = 1, rejected = 0)."""
    with session() as s:
        rows = [(r.basal, 1 if r.card.decision == "approved" else 0)
                for r in s.scalars(select(Record).join(Card, Card.record_id == Record.id)
                                   .where(Card.decision.in_(("approved", "rejected"))))
                if r.basal and r.basal.get("features")]
    return train_head(rows)


# ---------------------------------------------------------------- audiences (personas) + business case
@router.get("/personas")
def personas():
    from radar.business import PERSONAS

    return [{"key": k, **{f: v[f] for f in ("name", "icon", "promise", "cta", "metric")}} for k, v in PERSONAS.items()]


@router.get("/personas/{key}")
def persona(key: str, voivodeship: str | None = None, limit: int = 24):
    """Ideas matched to one audience, ranked by its money metric x quality, with deterministic business cases."""
    from radar.business import PERSONAS, business_case, dedup_key, is_infrastructure, metric_value

    p = PERSONAS.get(key)
    if p is None:
        raise HTTPException(404, "unknown audience")
    f = dict(p["filters"])
    with session() as s:
        recs = s.scalars(select(Record).join(Card, Card.record_id == Record.id)
                         .where(_filters(**f, voivodeship=voivodeship), Card.decision != "rejected")
                         .order_by(Card.score.desc().nulls_last()).limit(400)).all()
        rows, seen = [], set()
        for r in recs:  # recs are best-first, so the first of a programme/title group wins
            if is_infrastructure(r) or r.source_id in p.get("skip_sources", ()):
                continue
            k = dedup_key(r)
            if k in seen:
                continue
            seen.add(k)
            bc = business_case(r, r.card)
            d = idea_dict(r)
            d["business"] = {"metric": metric_value(bc, p["metric"]), "deploy_cost_pln": bc["deploy_cost_pln"],
                             "adopters": bc["adopters"], "som_3y_pln": bc["market"]["som_3y_pln"],
                             "funding": [x["programme"] for x in bc["funding"][:2]], "payback": bc["payback"]}
            rows.append(d)
    import math

    rows.sort(key=lambda d: -((d["score"] or 0) * .75 + min(25, 25 * math.log10(1 + d["business"]["metric"]) / 8)))
    top = rows[:min(limit, 60)]
    return {"key": key, **{k: p[k] for k in ("name", "icon", "promise", "cta", "metric")},
            "total": len(rows),
            "summary": {"ideas": len(rows), "metric_sum_pln": round(sum(d["business"]["metric"] for d in rows)),
                        "som_3y_sum_pln": round(sum(d["business"]["som_3y_pln"] for d in rows)),
                        "regions": len({d["voivodeship"] for d in rows if d["voivodeship"]})},
            "items": top}
