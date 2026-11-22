"""Pregeneration: everything a card needs on screen, computed once from the record and card, then stored.

Cost rule of the project: what can be computed in advance is computed once and served statically. This module is
the pure core: no database, no CLI, no Celery. Given a ``Record`` and its ``Card`` it returns

* ``brief``     one-page reel brief (the same deterministic brief the assess stage writes),
* ``slogan``    a short tagline ("hasło") for the reel and share cards,
* ``business``  the transparent business case from :mod:`radar.business`,
* ``audiences`` fit and ranking for every audience in ``radar.business.PERSONAS``,

plus ``inputs_hash`` so a nightly run recomputes only cards whose inputs changed.

All of it is rules: zero LLM calls. A small local model may refine the slogan only when a ``complete`` callable is
passed in explicitly (see :func:`slogan`); its output is validated and the rule-based slogan is the fallback.
Wiring into the CLI, the database and Celery beat waits for the Assess + Ops PR (#11).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Iterable

from radar.business import PERSONAS, business_case, dedup_key, is_infrastructure, metric_value

VERSION = "pregen/v1"
SLOGAN_MAX = 90
# fields of the record and card that change the output; anything else (likes, timestamps) does not
REC_FIELDS = ("title", "abstract", "source_id", "affiliations", "amounts", "sector", "tech_area", "innovation_type",
              "institution_type", "voivodeship", "cost_level")
# extraction providers that are not a large cloud model (None = rules / no extraction recorded)
SMALL_OR_NONE = (None, "", "rules", "reguły", "mock", "local")
CARD_FIELDS = ("solution_name", "problem_solved", "summary_pl", "maturity", "score", "decision", "assessment")


# ------------------------------------------------------------------------------------------------ helpers
def inputs_hash(rec, card) -> str:
    """Stable fingerprint of everything that feeds the pregenerated content."""
    payload = {"v": VERSION,
               "rec": {f: getattr(rec, f, None) for f in REC_FIELDS},
               "card": {f: getattr(card, f, None) for f in CARD_FIELDS}}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def needs_refresh(stored: dict | None, rec, card) -> bool:
    return not stored or stored.get("version") != VERSION or stored.get("inputs_hash") != inputs_hash(rec, card)


def shorten(text: str | None, limit: int) -> str:
    """First sentence/clause of ``text``, cut on a word boundary to at most ``limit`` characters."""
    t = re.sub(r"\s+", " ", (text or "")).strip().rstrip(".")
    t = re.split(r"(?<=[.!?;])\s", t, maxsplit=1)[0].rstrip(".;")
    if len(t) <= limit:
        return t
    cut = t[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:–- ")
    return cut + "…"


# ------------------------------------------------------------------------------------------------ brief
def reel_brief(rec, card) -> dict:
    """The reel brief. Uses the assess-stage brief when the card has a full assessment, else a minimal one."""
    a = card.assessment or {}
    if a.get("scores") and "total" in a:
        try:
            from radar.pipeline.assess import brief

            return brief(rec, card, a)
        except (KeyError, IndexError, TypeError):
            pass  # an older assessment shape: fall through to the minimal brief
    from radar.basal.classifier import label_pl

    return {
        "hook": card.problem_solved or rec.title,
        "solution": card.solution_name or rec.title,
        "summary": card.summary_pl or shorten(rec.abstract, 400) or None,
        "who": ", ".join((rec.affiliations or [])[:2]) or label_pl("institution_type", rec.institution_type),
        "where": rec.voivodeship,
        "tags": [label_pl("sector", rec.sector), label_pl("tech_area", rec.tech_area),
                 label_pl("innovation_type", rec.innovation_type)],
        "maturity": card.maturity, "cost": label_pl("cost_level", rec.cost_level),
        "for_whom": list(card.target_users or [])[:3],
        "next_step": None, "path": None, "score": card.score, "top_criteria": [], "metric": None, "against": None,
    }


# ------------------------------------------------------------------------------------------------ slogan
def rule_slogan(rec, card) -> str:
    """Deterministic tagline: "<solution> — <problem it solves>" when both fit, else the solution alone."""
    name = shorten(card.solution_name or rec.title, 60) or "Innowacja"
    problem = shorten(card.problem_solved, SLOGAN_MAX)
    if problem and problem.lower() != name.lower():
        both = f"{name} — {problem[0].lower()}{problem[1:]}"
        if len(both) <= SLOGAN_MAX:
            return both
    return shorten(name, SLOGAN_MAX)


SLOGAN_SYSTEM = ("Jesteś redaktorem portalu o innowacjach z polskich szkół, uczelni i samorządów. Piszesz po polsku, "
                 "krótko i rzeczowo, bez nowych faktów, liczb ani nazw spoza tekstu. Odpowiadasz wyłącznie JSON.")


def slogan_prompt(rec, card) -> str:
    return (f"Tytuł: {card.solution_name or rec.title}\n"
            f"Problem: {card.problem_solved or '-'}\n"
            f"Opis: {shorten(card.summary_pl or rec.abstract, 600)}\n\n"
            f'Zwróć JSON {{"haslo": "..."}}: jedno hasło do rolki, maksymalnie {SLOGAN_MAX} znaków, '
            "mówiące komu i w czym to pomaga.")


# GBNF for llama.cpp: forces {"haslo": "..."} of 10-90 characters. A 1.5B model ignores "JSON only" in the prompt,
# and this llama.cpp build fails on response_format/json_schema ("Failed to initialize samplers"); raw GBNF works.
SLOGAN_GBNF = r'''root ::= "{\"haslo\": \"" [^"\\\n]{10,90} "\"}"'''

_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_DANGLING = re.compile(r"(?:\b(?:i|w|we|z|ze|do|na|dla|oraz|o|od|po|przez|a|ale|lub|czy|że|aby|który|która|które)|[,:;–-])$",
                       re.I)


def validate_slogan(text, rec, card) -> str | None:
    """Accept a model's slogan only if it is short, complete and adds no numbers absent from the source."""
    if not isinstance(text, str):
        return None
    if len(text.strip()) >= SLOGAN_MAX - 1:  # hit the grammar's length cap: cut mid-word, not a finished slogan
        return None
    t = re.sub(r"\s+", " ", text.replace("**", "").replace("__", "")).strip().strip('"„”*/ ')
    if not 8 <= len(t) <= SLOGAN_MAX:
        return None
    source = " ".join(filter(None, (rec.title, rec.abstract, card.solution_name, card.problem_solved, card.summary_pl)))
    known = set(_NUM.findall(source))
    if any(n not in known for n in _NUM.findall(t)):
        return None
    if _DANGLING.search(t):  # cut off by the length limit mid-phrase
        return None
    return t


def slogan(rec, card, complete: Callable[[str, str], dict] | None = None) -> tuple[str, str]:
    """Return ``(slogan, by)``. ``by`` is "reguły" or "local-llm". The LLM is used only when ``complete`` is given."""
    if complete is not None:
        try:
            out = complete(SLOGAN_SYSTEM, slogan_prompt(rec, card))
            ok = validate_slogan((out or {}).get("haslo"), rec, card)
            if ok:
                return ok, "local-llm"
        except Exception:  # noqa: BLE001 - any model failure falls back to the rule-based slogan
            pass
    return rule_slogan(rec, card), "reguły"


# ------------------------------------------------------------------------------------------------ audiences
def fits_persona(rec, card, persona: dict) -> bool:
    """Same filter the /api/personas/{key} endpoint applies, evaluated on one record."""
    if card.decision == "rejected" or is_infrastructure(rec) or rec.source_id in persona.get("skip_sources", ()):
        return False
    for axis, val in persona["filters"].items():
        have = card.maturity if axis == "maturity" else getattr(rec, axis, None)
        if have not in val.split(","):
            return False
    return True


def audience_rank(score: float | None, metric: float) -> float:
    """Ranking used by the audience pages: quality x the audience's money metric."""
    return (score or 0) * .75 + min(25, 25 * math.log10(1 + max(0, metric)) / 8)


def audiences(rec, card, bc: dict) -> dict:
    out = {}
    for key, p in PERSONAS.items():
        m = metric_value(bc, p["metric"])
        out[key] = {"fits": fits_persona(rec, card, p), "metric": p["metric"], "value": m,
                    "rank": round(audience_rank(card.score, m), 2)}
    return out


# ------------------------------------------------------------------------------------------------ entry points
def pregenerate(rec, card, complete: Callable[[str, str], dict] | None = None) -> dict:
    """All pregenerated content for one card. Pure: same inputs, same output (unless ``complete`` is given)."""
    bc = business_case(rec, card)
    aud = audiences(rec, card, bc)
    text, by = slogan(rec, card, complete)
    return {
        "version": VERSION,
        "inputs_hash": inputs_hash(rec, card),
        "dedup_key": dedup_key(rec),
        "brief": reel_brief(rec, card),
        "slogan": text,
        "slogan_by": by,
        "business": bc,
        "audiences": aud,
        "top_audiences": sorted((k for k, v in aud.items() if v["fits"]), key=lambda k: -aud[k]["rank"]),
        "llm_calls": 1 if complete is not None else 0,
    }


def pregenerate_many(pairs: Iterable[tuple], stored: dict | None = None) -> tuple[dict, dict]:
    """Pregenerate many ``(record, card)`` pairs, skipping cards whose stored content is still current.

    ``stored`` maps card id -> previously stored pregen dict. Returns ``(results by card id, stats)``; stats count
    how many cards were computed and skipped, and how many never touched a large cloud model (pregen itself is
    rules-only; the card's extraction provenance tells whether a cloud model wrote the card).
    """
    stored = stored or {}
    results, stats = {}, {"cards": 0, "computed": 0, "skipped": 0, "no_large_llm": 0}
    for rec, card in pairs:
        stats["cards"] += 1
        if (card.provenance or {}).get("provider") in SMALL_OR_NONE:
            stats["no_large_llm"] += 1
        if not needs_refresh(stored.get(card.id), rec, card):
            stats["skipped"] += 1
            continue
        results[card.id] = pregenerate(rec, card)
        stats["computed"] += 1
    stats["no_large_llm_pct"] = round(100 * stats["no_large_llm"] / stats["cards"], 1) if stats["cards"] else 0.0
    return results, stats
