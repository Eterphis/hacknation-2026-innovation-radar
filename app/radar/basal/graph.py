"""Idea graph: kNN similarity edges between records + hub nodes (sector, technology area, voivodeship,
institution) derived from Basal labels, so the UI can show an Obsidian-like graph and the agent can traverse it.

Similarity is computed in numpy over stored embeddings (fine up to tens of thousands of records on one vCPU);
pgvector is the drop-in upgrade when it grows (see main-flow.md).
"""

from __future__ import annotations

import numpy as np
from sqlalchemy import delete, or_, select

from radar.basal.embed import get_embedder
from radar.models import Edge, Record

SIMILAR_MIN = 0.2  # calibrated on demo data for hashing-stem6+char4 (median pair 0.08, p95 0.24)
DUP_MIN = 0.9
TOP_K = 6
INDEXED = ("extracted", "ready")


def record_text(r: Record) -> str:
    return " ".join(filter(None, [r.title, r.abstract, " ".join(r.keywords or [])]))


def index_record(s, rec: Record) -> list[dict]:
    """Embed the record and (re)build its similarity edges. Returns the neighbours found."""
    vec = get_embedder().embed_one(record_text(rec))
    rec.embedding = vec.round(5).tolist()
    others = s.execute(select(Record.id, Record.embedding, Record.voivodeship, Record.institution_type)
                       .where(Record.id != rec.id, Record.embedding.is_not(None), Record.status.in_(INDEXED))).all()
    s.execute(delete(Edge).where(or_(Edge.src_id == rec.id, Edge.dst_id == rec.id)))
    if not others:
        return []
    ids = [o.id for o in others]
    M = np.array([o.embedding for o in others], dtype=np.float32)
    if M.shape[1] != vec.shape[0]:  # embedder changed: skip until re-index
        return []
    sims = M @ vec
    order = np.argsort(-sims)[:TOP_K]
    found = []
    for i in order:
        sim = float(sims[i])
        if sim < SIMILAR_MIN:
            break
        kind = "possible_duplicate" if sim >= DUP_MIN else "similar"
        a, b = sorted((rec.id, ids[i]))
        s.add(Edge(src_id=a, dst_id=b, kind=kind, weight=round(sim, 4)))
        found.append({"record_id": ids[i], "similarity": round(sim, 3), "kind": kind,
                      "voivodeship": others[i].voivodeship, "institution_type": others[i].institution_type})
    return found


def similar(s, rec: Record, k: int = 5) -> list[dict]:
    rows = s.execute(select(Edge).where(or_(Edge.src_id == rec.id, Edge.dst_id == rec.id))
                     .order_by(Edge.weight.desc()).limit(k)).scalars().all()
    out = []
    for e in rows:
        other = s.get(Record, e.dst_id if e.src_id == rec.id else e.src_id)
        if other is not None:
            out.append({"record_id": other.id, "title": other.title, "similarity": e.weight, "kind": e.kind,
                        "voivodeship": other.voivodeship, "institution_type": other.institution_type,
                        "card_id": other.card.id if other.card else None})
    return out


def build_graph(s, records: list[Record], hubs: tuple[str, ...] = ("sector", "tech_area", "voivodeship")) -> dict:
    """Nodes + links for the UI. Idea nodes link to each other (similarity) and to hub nodes."""
    from radar.basal.classifier import label_pl

    ids = {r.id for r in records}
    nodes, links, hub_seen = [], [], set()
    for r in records:
        c = r.card
        nodes.append({"id": f"r{r.id}", "type": "idea", "label": (c.solution_name if c and c.solution_name else r.title or "")[:80],
                      "card_id": c.id if c else None, "score": c.score if c else None, "sector": r.sector,
                      "voivodeship": r.voivodeship, "maturity": c.maturity if c else None})
        for axis in hubs:
            v = getattr(r, axis)
            if not v:
                continue
            hid = f"{axis}:{v}"
            if hid not in hub_seen:
                hub_seen.add(hid)
                nodes.append({"id": hid, "type": axis, "label": label_pl(axis, v) if axis != "voivodeship" else v})
            links.append({"source": f"r{r.id}", "target": hid, "kind": axis, "weight": 0.3})
    if ids:
        for e in s.execute(select(Edge).where(Edge.src_id.in_(ids), Edge.dst_id.in_(ids))).scalars():
            links.append({"source": f"r{e.src_id}", "target": f"r{e.dst_id}", "kind": e.kind, "weight": e.weight})
    return {"nodes": nodes, "links": links}
