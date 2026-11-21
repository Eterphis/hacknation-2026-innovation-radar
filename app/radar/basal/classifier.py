"""Basal: fast, explainable multi-axis classifier that runs before (gate) and after (recheck) any LLM.

One call classifies every axis at once: decision (accept/hold/reject), sector, technology area, innovation type,
institution type, maturity hint, cost level, voivodeship, priority. Each axis = keyword evidence + similarity to a
label prototype in embedding space; an optional learned head (logistic regression on operator decisions) adjusts
the accept score. No LLM, milliseconds per record, plain vCPU.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from radar.basal import taxonomy as T
from radar.basal.embed import fold, get_embedder

VERSION = "basal/v1"
KW_WEIGHT, PROTO_WEIGHT = 0.65, 0.35
PII = {
    "pesel": re.compile(r"\b\d{11}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "telefon": re.compile(r"(?<!\d)(?:\+48[ -]?)?(?:\d{3}[ -]?\d{3}[ -]?\d{3}|\d{2}[ -]\d{3}[ -]\d{2}[ -]\d{2})(?!\d)"),
}


@dataclass
class Label:
    value: str | None
    confidence: float
    by: str
    evidence: list[str] = field(default_factory=list)
    alternatives: list[tuple[str, float]] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"value": self.value, "confidence": round(self.confidence, 3), "by": self.by,
                "evidence": self.evidence[:6], "alternatives": [(a, round(s, 3)) for a, s in self.alternatives[:3]]}


def _compile(table: dict[str, dict]) -> dict[str, list[re.Pattern]]:
    return {k: [re.compile(p) for p in v["kw"]] for k, v in table.items()}


_SECT, _TECH, _ITYPE, _INST = (_compile(t) for t in (T.SECTORS, T.TECH_AREAS, T.INNOVATION_TYPES, T.INSTITUTION_TYPES))
_RX = {name: [re.compile(p) for p in pats] for name, pats in
       {"negative": T.NEGATIVE, "spam": T.SPAM, "offensive": T.OFFENSIVE, "signal": T.SIGNAL}.items()}
_MAT = {k: [re.compile(p) for p in v] for k, v in T.MATURITY_KW.items()}
_COST = {k: [re.compile(p) for p in v] for k, v in T.COST_KW.items()}


@lru_cache
def _prototypes(axis: str) -> tuple[list[str], np.ndarray]:
    table = {"sector": T.SECTORS, "tech": T.TECH_AREAS, "itype": T.INNOVATION_TYPES}[axis]
    keys = list(table)
    return keys, get_embedder().embed([table[k]["proto"] for k in keys])


def _hits(text: str, pats: list[re.Pattern]) -> list[str]:
    out = []
    for p in pats:
        m = p.search(text)
        if m:
            out.append(m.group(0))
    return out


def _axis(text: str, vec: np.ndarray, compiled: dict, axis: str, min_conf: float = 0.2) -> Label:
    keys, protos = _prototypes(axis)
    sims = dict(zip(keys, (protos @ vec).tolist()))
    hits = {k: _hits(text, pats) for k, pats in compiled.items()}
    max_hits = max((len(h) for h in hits.values()), default=0) or 1
    scores = {}
    for k in keys:
        kw = len(hits[k]) / max_hits if hits[k] else 0.0
        sim = max(0.0, sims[k])
        scores[k] = KW_WEIGHT * kw + PROTO_WEIGHT * sim
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    best, s = ranked[0]
    margin = s - (ranked[1][1] if len(ranked) > 1 else 0)
    conf = min(1.0, s * 0.8 + margin)
    if s < 0.12 or conf < min_conf:
        return Label(None, conf, "brak sygnałów", [], ranked[:3])
    by = "słownik+prototyp" if hits[best] else "prototyp"
    return Label(best, conf, by, hits[best], ranked[1:4])


def _institution(text: str, declared: str | None) -> Label:
    if declared:
        key = T.INSTITUTION_FIELD_MAP.get(declared.strip(), T.INSTITUTION_FIELD_MAP.get(declared.strip().lower()))
        if key:
            return Label(key, 0.95, "pole zgłoszenia", [declared])
    hits = {k: _hits(text, pats) for k, pats in _INST.items()}
    ranked = sorted(((k, len(v)) for k, v in hits.items()), key=lambda kv: -kv[1])
    k, n = ranked[0]
    if not n:
        return Label("unknown", 0.0, "brak sygnałów")
    # a public institution named anywhere beats a company form (consortia: uczelnia + sp. z o.o.)
    if k == "firma":
        public = [kk for kk, nn in ranked if nn and kk != "firma"]
        if public:
            k = public[0]
    return Label(k, min(0.9, 0.5 + 0.15 * len(hits[k])), "słownik (do potwierdzenia rejestrem: T023)", hits[k])


def _maturity(text: str, kind: str) -> Label:
    if kind == "patent":
        return Label("tech_ready", 0.9, "rodzaj rekordu: patent", ["patent"])
    for level in ("market_ready", "business_ready", "tech_ready", "exploring"):
        h = _hits(text, _MAT[level])
        if h:
            return Label(level, 0.6 if level != "exploring" else 0.4, "słownik", h)
    return Label("exploring", 0.2, "domyślnie")


def _cost(amounts: dict, text: str) -> Label:
    vals = [v for k, v in (amounts or {}).items() if isinstance(v, (int, float)) and v > 0]
    if vals:
        v = max(vals)
        level = "niski" if v < 1e5 else "sredni" if v < 2e6 else "wysoki" if v < 2e7 else "bardzo_wysoki"
        return Label(level, 0.9, "kwota w rekordzie", [f"{v:,.0f} zł".replace(",", " ")])
    for level in ("bardzo_wysoki", "wysoki", "niski"):
        h = _hits(text, _COST[level])
        if h:
            return Label(level, 0.5, "słownik", h)
    return Label("sredni", 0.2, "domyślnie (brak kwot)")


def voivodeship(*texts: str | None) -> Label:
    t = fold(" ".join(x for x in texts if x))
    for key, name in T.VOIVODESHIPS.items():
        if key in t:
            return Label(name, 0.95, "nazwa województwa", [key])
    for city, name in T.CITY_VOIV.items():
        if re.search(r"\b" + city, t):
            return Label(name, 0.8, "miasto", [city])
    return Label(None, 0.0, "brak")


def mask_pii(text: str | None) -> tuple[str | None, list[str]]:
    if not text:
        return text, []
    found = []
    for name, rx in PII.items():
        if rx.search(text):
            found.append(name)
            text = rx.sub(f"[{name} ukryty]", text)
    return text, found


# --------------------------------------------------------------------------- learned head
HEAD_KEY = "basal.head"
_head_cache: dict = {"w": None, "at": 0.0}


def _features(lbl: dict, text_len: int, n_signal: int) -> np.ndarray:
    f = [1.0, min(text_len, 2000) / 2000, min(n_signal, 8) / 8,
         lbl["sector"]["confidence"], lbl["tech_area"]["confidence"], lbl["innovation_type"]["confidence"],
         1.0 if lbl["institution_type"]["value"] in ("szkola", "uczelnia", "instytut", "jst", "inna_publiczna") else 0.0,
         ["exploring", "tech_ready", "business_ready", "market_ready"].index(lbl["maturity_hint"]["value"]) / 3]
    return np.array(f, dtype=np.float32)


def train_head(rows: list[tuple[dict, int]], epochs: int = 400, lr: float = 0.5) -> dict:
    """rows: (basal_result, 1=approved / 0=rejected). Plain logistic regression, numpy."""
    if len(rows) < 6 or len({y for _, y in rows}) < 2:
        return {"trained": False, "reason": "za mało decyzji (min. 6, obie klasy)"}
    X = np.vstack([np.array(b["features"], dtype=np.float32) for b, _ in rows])
    y = np.array([yy for _, yy in rows], dtype=np.float32)
    w = np.zeros(X.shape[1], dtype=np.float32)
    for _ in range(epochs):
        p = 1 / (1 + np.exp(-(X @ w)))
        w -= lr * (X.T @ (p - y) / len(y) + 0.01 * w)
    acc = float(((1 / (1 + np.exp(-(X @ w))) > 0.5) == (y > 0.5)).mean())
    from radar.db import session
    from radar.models import Setting

    with session() as db:  # stored in the DB so every pod (api, workers) uses the same head
        row = db.get(Setting, HEAD_KEY) or Setting(key=HEAD_KEY)
        row.value = {"w": w.tolist(), "n": len(rows), "train_acc": acc}
        db.add(row)
    _head_cache["at"] = 0.0
    return {"trained": True, "n": len(rows), "train_acc": round(acc, 3)}


def _head(ttl: float = 60.0) -> np.ndarray | None:
    import time

    if time.monotonic() - _head_cache["at"] < ttl:
        return _head_cache["w"]
    w = None
    try:
        from radar.db import session
        from radar.models import Setting

        with session() as db:
            row = db.get(Setting, HEAD_KEY)
            if row and row.value.get("w"):
                w = np.array(row.value["w"], dtype=np.float32)
    except Exception:  # no DB in a pure-classification context: rules + prototypes only
        w = None
    _head_cache.update(w=w, at=time.monotonic())
    return w


# --------------------------------------------------------------------------- main entry
def classify(*, title: str | None, abstract: str | None, keywords: list[str] | None = None,
             affiliations: list[str] | None = None, region: str | None = None, kind: str = "other",
             amounts: dict | None = None, declared_institution: str | None = None,
             duplicate_of: int | None = None, min_chars: int = 200) -> dict:
    raw_text = " ".join(filter(None, [title, abstract, " ".join(keywords or [])]))
    text = fold(raw_text)
    org_text = fold(" ".join(affiliations or []))
    vec = get_embedder().embed_one(raw_text)

    labels = {
        "sector": _axis(text, vec, _SECT, "sector"),
        "tech_area": _axis(text, vec, _TECH, "tech"),
        "innovation_type": _axis(text, vec, _ITYPE, "itype"),
        "institution_type": _institution(org_text + " " + text, declared_institution),
        "maturity_hint": _maturity(text, kind),
        "cost_level": _cost(amounts or {}, text),
        "voivodeship": voivodeship(region, " ".join(affiliations or []), abstract),
    }
    out = {k: v.as_dict() for k, v in labels.items()}

    # ---- gate
    reasons, hold = [], []
    n_signal = len(_hits(text, _RX["signal"]))
    if not title or not abstract:
        reasons.append("za mało informacji: brak tytułu lub opisu")
    elif len(abstract) < min_chars:
        reasons.append(f"za mało informacji: opis krótszy niż {min_chars} znaków")
    if duplicate_of:
        reasons.append(f"duplikat rekordu #{duplicate_of}")
    if (h := _hits(text, _RX["offensive"])):
        reasons.append("treść obraźliwa")
    if (h := _hits(text, _RX["spam"])):
        reasons.append(f"spam / reklama ({', '.join(h)})")
    if (h := _hits(text, _RX["negative"])) and n_signal < 2:
        reasons.append(f"nie dotyczy innowacji ({', '.join(h)})")
    if n_signal == 0 and kind in ("publication", "other"):
        reasons.append("brak opisu rozwiązania (słowa: opracowano, wdrożenie, prototyp, metoda, usługa…)")
    if labels["institution_type"].value == "firma":
        reasons.append("poza zakresem: tylko firma prywatna, brak instytucji publicznej")
    if labels["institution_type"].value == "unknown":
        hold.append("typ instytucji nieustalony")
    if labels["sector"].value is None:
        hold.append("sektor nieustalony")
    _, pii = mask_pii(" ".join(filter(None, [title, abstract])))
    if pii:
        hold.append(f"dane osobowe w treści ({', '.join(pii)}): zamaskowane")

    feats = _features(out, len(abstract or ""), n_signal)
    w = _head()
    learned = float(1 / (1 + np.exp(-(feats @ w)))) if w is not None and len(w) == len(feats) else None

    confs = [labels[a].confidence for a in ("sector", "tech_area", "innovation_type", "institution_type")]
    completeness = sum(1 for x in (title, abstract, affiliations, region, amounts) if x) / 5
    mat_bonus = {"exploring": 0.0, "tech_ready": 0.25, "business_ready": 0.15, "market_ready": 0.05}[labels["maturity_hint"].value]
    priority = 0.45 * float(np.mean(confs)) + 0.3 * completeness + mat_bonus
    if learned is not None:
        priority = 0.6 * priority + 0.4 * learned
    if hold:
        priority *= 0.6

    if reasons:
        decision = "reject"
    elif pii or (labels["institution_type"].value == "unknown" and labels["sector"].value is None):
        decision = "hold"  # operator looks first: personal data, or nothing to route on
    else:
        decision = "accept"
    out.update({
        "version": VERSION, "embedder": get_embedder().name,
        "decision": decision, "reject_reasons": reasons, "hold_reasons": hold, "pii": pii,
        "priority": round(min(priority, 1.0), 3), "learned_accept": None if learned is None else round(learned, 3),
        "routing_key": f"task.{labels['institution_type'].value or 'unknown'}.{labels['innovation_type'].value or 'unknown'}",
        "features": feats.round(4).tolist(),
    })
    return out


def label_pl(axis: str, value: str | None) -> str:
    table = {"sector": T.SECTORS, "tech_area": T.TECH_AREAS, "innovation_type": T.INNOVATION_TYPES,
             "institution_type": T.INSTITUTION_TYPES}.get(axis)
    if axis == "cost_level":
        return T.COST_PL.get(value or "", value or "—")
    if table and value in table:
        return table[value]["pl"]
    return value or "—"
