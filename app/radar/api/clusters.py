"""Two more ways to see the whole collection at once, both without an LLM:

- tematy: k-means on the embeddings Basal already stored (cosine, k-means++ seeded, deterministic), each cluster named by
  the words that are frequent inside it and rare outside it (c-TF-IDF over titles), with size, quality, community
  likes, regions and maturity mix
- rynki: the same ideas grouped by who would buy them (adopter type from the business case), with the market size,
  so an implementer sees whole markets, not single records
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

import numpy as np
from fastapi import APIRouter
from sqlalchemy import select

from radar.api.cache import cached
from radar.basal.classifier import label_pl
from radar.basal.embed import fold
from radar.db import session
from radar.models import Card, Record

router = APIRouter(prefix="/api")
STOP = set("""oraz przez ktore ktora ktory ktorych jako jest bylo byly beda dzieki takze tego tych tej jego jej ich nowych nowej
nowego nowe innych ramach projekt projektu projektow projekcie rozwoj rozwoju systemu system systemow badania badan
zastosowanie zastosowania metody metoda opracowanie opracowania wykorzystanie wykorzystaniem analiza analizy poprzez
oparciu podstawie celu ponad wraz miedzy pomiedzy wsrod sposob sposobu bardziej mozliwosci technologii technologia
polsce polski polska polskiej programu program wdrozenie wdrozenia innowacyjnego innowacyjnej innowacyjny innowacyjne
with from that this their which using based study analysis new development system systems project research""".split())
LVLS = ["exploring", "tech_ready", "business_ready", "market_ready"]


def _rows():
    from radar.business import dedup_key, is_infrastructure

    with session() as s:
        recs = s.scalars(select(Record).join(Card, Card.record_id == Record.id)
                         .where(Record.status.in_(("extracted", "ready")), Card.decision != "rejected")).all()
        out, seen = [], set()
        for r in recs:
            if not r.embedding or is_infrastructure(r):
                continue
            k = dedup_key(r)
            if k in seen:
                continue
            seen.add(k)
            from radar.api.explore import idea_dict

            d = idea_dict(r)
            d["_emb"] = r.embedding
            d["_text"] = fold(f"{r.title or ''} {' '.join(r.keywords or [])}")
            out.append(d)
        return out


def _kmeans(x: np.ndarray, k: int, iters: int = 30, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    centers = [x[rng.integers(len(x))]]
    for _ in range(1, k):  # k-means++
        d = np.min(1 - x @ np.stack(centers).T, axis=1).clip(0)
        centers.append(x[rng.choice(len(x), p=d / d.sum())] if d.sum() > 0 else x[rng.integers(len(x))])
    c = np.stack(centers)
    lab = np.zeros(len(x), dtype=int)
    for _ in range(iters):
        new = np.argmax(x @ c.T, axis=1)
        if np.array_equal(new, lab) and _ > 0:
            break
        lab = new
        for j in range(k):
            m = x[lab == j]
            if len(m):
                v = m.mean(axis=0)
                c[j] = v / (np.linalg.norm(v) or 1)
    return lab


def _words(t: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]{4,}", t) if w not in STOP]


def _summary(items: list[dict]) -> dict:
    mat = Counter(i["maturity"] for i in items)
    sec = Counter(i["sector"] for i in items if i["sector"])
    top = sorted(items, key=lambda i: -((i["score"] or 0) + 3 * (i["likes"] or 0)))
    return {"size": len(items), "avg_score": round(sum(i["score"] or 0 for i in items) / max(1, len(items)), 1),
            "likes": sum(i["likes"] or 0 for i in items), "regions": len({i["voivodeship"] for i in items if i["voivodeship"]}),
            "ready": sum(mat[m] for m in ("business_ready", "market_ready")),
            "maturity": [mat.get(m, 0) for m in LVLS],
            "sector": sec.most_common(1)[0][0] if sec else None,
            "items": [{k: v for k, v in i.items() if not k.startswith("_")} for i in top[:6]]}


def _named(groups: dict, namer) -> list[dict]:
    """Summaries + distinctive words per group (c-TF-IDF: frequent inside, rare in other groups)."""
    docs = {g: Counter(w for d in items for w in set(_words(d["_text"]))) for g, items in groups.items()}
    df = Counter()
    for c in docs.values():
        df.update(set(c))
    k = max(1, len(groups))
    out = []
    for g, items in groups.items():
        n = len(items)
        score = {w: (cnt / n) * math.log(1 + k / df[w]) for w, cnt in docs[g].items() if cnt >= max(2, n * .06)}
        summ = _summary(items)
        out.append({"key": "|".join(g) if isinstance(g, tuple) else str(g), "name": namer(g, summ),
                    "tech_area": g[0] if isinstance(g, tuple) else None, "keywords": [w for w, _ in sorted(score.items(), key=lambda t: -t[1])[:5]], **summ})
    out.sort(key=lambda c: -c["size"])
    return out


@router.get("/clusters")
def clusters(mode: str = "tematy", k: int = 10):
    # was a 10-minute TTL dict without invalidation: a new card stayed invisible here; now keyed by the data version
    return cached("clusters", (mode, k), lambda: _clusters(mode, k))


def _clusters(mode: str, k: int) -> dict:
    rows = _rows()
    if mode == "rynki":
        from radar.business import ADOPTERS, adopter_key, adopters_for

        groups: dict = defaultdict(list)
        with session() as s:
            recs = {r.id: r for r in s.scalars(select(Record).where(Record.id.in_([d["record_id"] for d in rows])))}
            for d in rows:
                groups[adopter_key(recs[d["record_id"]])].append(d)
        out = []
        for g, items in groups.items():
            a = adopters_for(g)
            out.append({"key": g, "name": a["who"].split(" (")[0], "adopters": a["count"], **_summary(items)})
        out.sort(key=lambda c: -c["size"])
        res = {"mode": mode, "total": len(rows), "clusters": out}
    elif mode == "podobne":
        # embedding k-means: groups that cut across sectors (same method, different field)
        if len(rows) < k:
            return {"mode": mode, "total": len(rows), "clusters": []}
        x = np.array([d["_emb"] for d in rows], dtype=np.float32)
        x /= np.linalg.norm(x, axis=1, keepdims=True).clip(1e-9)
        lab = _kmeans(x, k)
        groups = defaultdict(list)
        for d, l in zip(rows, lab):
            groups[f"k{l}"].append(d)
        res = {"mode": mode, "total": len(rows), "clusters": _named(groups, lambda g, s: label_pl("sector", s["sector"]).split(",")[0] if s["sector"] else "Inne")}
    else:
        # tematy: technology x sector, the way an investor or a ministry thinks about a portfolio ("AI w zdrowiu")
        groups = defaultdict(list)
        for d in rows:
            if d["sector"] and d["tech_area"]:
                groups[(d["tech_area"], d["sector"])].append(d)
        groups = {g: v for g, v in groups.items() if len(v) >= max(2, min(6, len(rows) // 60))}  # small corpora still group
        top = dict(sorted(groups.items(), key=lambda t: -len(t[1]))[:max(6, min(k + 4, 20))])
        name = lambda g, s: f"{label_pl('tech_area', g[0]).split(' (')[0]} · {label_pl('sector', g[1]).split(',')[0]}"
        res = {"mode": mode, "total": len(rows), "clusters": _named(top, name)}
    return res
