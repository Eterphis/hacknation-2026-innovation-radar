"""Pregeneration: everything a card needs on screen, computed once from the record and card, then stored.

Cost rule of the project: what can be computed in advance is computed once and served statically. This module is
the pure core: no database, no CLI, no Celery. Given a ``Record`` and its ``Card`` it returns

* ``brief``     one-page reel brief (the same deterministic brief the assess stage writes),
* ``slogan``    a short tagline ("hasło") for the reel and share cards,
* ``business``  the transparent business case from :mod:`radar.business`,
* ``audiences`` fit and ranking for every audience in ``radar.business.PERSONAS``,

plus ``inputs_hash`` so a nightly run recomputes only cards whose inputs changed.

All of it is rules: zero LLM calls. A small local model may refine the slogan only when a ``complete`` callable is
passed in explicitly (see :func:`slogan`, :func:`with_model_slogan`); its output is validated and the rule-based
slogan is the fallback. The model is never called inside a database transaction (see :func:`run`).
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
def slogan_key(rec, card) -> str:
    """Fingerprint of the text a slogan is written from. A new score or assessment does not change it, so the
    daily reassess does not ask the model again for the same slogan."""
    raw = "\x1f".join(str(x or "") for x in (SLOGAN_SYSTEM, rec.title, rec.abstract, card.solution_name,
                                             card.problem_solved, card.summary_pl))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def pregenerate(rec, card, complete: Callable[[str, str], dict] | None = None, reuse: bool = True) -> dict:
    """All pregenerated content for one card. Pure: same inputs, same output (unless ``complete`` is given).
    ``reuse``: keep the stored slogan when its source text is unchanged (``card.pregen``), with no model call. A
    stored rule slogan is not reused when a model is given and has tries left (see :func:`wants_model_slogan`)."""
    bc = business_case(rec, card)
    aud = audiences(rec, card, bc)
    key, prev = slogan_key(rec, card), getattr(card, "pregen", None) or {}
    same = prev.get("slogan_key") == key and prev.get("slogan")
    tries = prev.get("slogan_tries", 0) if same else 0
    if reuse and same and (complete is None or not wants_model_slogan(prev)):  # computed once; `--force` redoes it
        text, by, calls = prev["slogan"], prev["slogan_by"], 0
    else:
        (text, by), calls = slogan(rec, card, complete), int(complete is not None)
        tries = 0 if by != RULES else tries + calls
    return {
        "version": VERSION,
        "inputs_hash": inputs_hash(rec, card),
        "dedup_key": dedup_key(rec),
        "brief": reel_brief(rec, card),
        "slogan": text,
        "slogan_by": by,
        "slogan_key": key,
        "slogan_tries": tries,
        "business": bc,
        "audiences": aud,
        "top_audiences": sorted((k for k, v in aud.items() if v["fits"]), key=lambda k: -aud[k]["rank"]),
        "llm_calls": calls,
    }


def pregenerate_many(pairs: Iterable[tuple], stored: dict | None = None,
                     complete: Callable[[str, str], dict] | None = None, reuse: bool = True) -> tuple[dict, dict]:
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
        results[card.id] = pregenerate(rec, card, complete, reuse)
        stats["computed"] += 1
    stats["no_large_llm_pct"] = round(100 * stats["no_large_llm"] / stats["cards"], 1) if stats["cards"] else 0.0
    return results, stats


# ------------------------------------------------------------------------------------------------ model slogan
# The model is never called inside a database transaction: callers compute the rule content in the transaction,
# take a detached snapshot (slogan_inputs), call the model outside, and write the result in a short transaction.
RULES, LOCAL = "reguły", "local-llm"
MAX_SLOGAN_TRIES = 3  # the model answered but its slogan failed validation this many times: keep the rule slogan


def wants_model_slogan(pg: dict | None) -> bool:
    """A stored rule slogan the local model may still improve (unavailable model = no try counted)."""
    return bool(pg) and pg.get("slogan_by") == RULES and pg.get("slogan_tries", 0) < MAX_SLOGAN_TRIES


def slogan_inputs(rec, card) -> tuple:
    """Detached copy of the fields the slogan prompt and its validation read (safe after the session closes)."""
    from types import SimpleNamespace

    return (SimpleNamespace(title=rec.title, abstract=rec.abstract),
            SimpleNamespace(**{f: getattr(card, f, None) for f in ("solution_name", "problem_solved", "summary_pl")}))


def with_model_slogan(pg: dict, rec, card, complete: Callable[[str, str], dict]) -> dict:
    """Ask the model for a slogan and return an updated copy of ``pg``. A model that is down (exception) leaves
    ``pg`` unchanged and counts no try, so the next run retries; a bad answer counts a try."""
    try:
        ans = complete(SLOGAN_SYSTEM, slogan_prompt(rec, card))
    except Exception:  # noqa: BLE001 - unavailable model: keep the rule slogan, try again later
        return pg
    ok = validate_slogan(ans.get("haslo") if isinstance(ans, dict) else None, rec, card)
    out = {**pg, "llm_calls": pg.get("llm_calls", 0) + 1}
    if ok:
        out.update(slogan=ok, slogan_by=LOCAL, slogan_tries=0)
    else:
        out["slogan_tries"] = pg.get("slogan_tries", 0) + 1
    return out


# ------------------------------------------------------------------------------------------------ storage
def store(rec, card, force: bool = False) -> bool:
    """Write ``card.pregen`` when missing or stale, rules only (it runs inside reassess's transaction; the stored
    model slogan is reused, a missing one is written by the next :func:`run`). True when it was (re)computed."""
    if not force and not needs_refresh(card.pregen, rec, card):
        return False
    card.pregen = pregenerate(rec, card, None, reuse=not force)
    return True


def run(force: bool = False, batch: int = 200, llm_budget_s: float | None = None) -> dict:
    """Pregenerate every scored card in the database (``radar pregenerate``, nightly beat).

    Two phases, so no transaction ever waits on the model: (1) rules for every stale card, one short transaction
    per ``batch``; (2) slogans from the small local model, outside any transaction, each written in its own short
    transaction, until ``llm_budget_s`` runs out (default ``RADAR_PREGEN_LLM_BUDGET_S``, below the Celery time
    limit) or the model's circuit breaker opens. Cards left over keep their rule slogan until the next run."""
    import time

    from sqlalchemy import select

    from radar.config import get_settings
    from radar.db import session
    from radar.models import Card, Record

    with session() as s:
        ids = s.scalars(select(Card.id).join(Record, Card.record_id == Record.id)
                        .where(Record.status.in_(("extracted", "ready")), Card.score.is_not(None))
                        .order_by(Card.id)).all()
    complete = local_slogan()
    stats = {"cards": 0, "computed": 0, "skipped": 0, "no_large_llm": 0}
    todo: list[tuple] = []  # (card id, slogan_key, rec snapshot, card snapshot)
    for i in range(0, len(ids), batch):
        with session() as s:
            cards = s.scalars(select(Card).where(Card.id.in_(ids[i:i + batch]))).all()
            stored = {} if force else {c.id: c.pregen for c in cards}
            results, st = pregenerate_many([(c.record, c) for c in cards], stored, None, reuse=not force)
            for c in cards:
                if c.id in results:
                    c.pregen = results[c.id]
                if complete is not None and wants_model_slogan(c.pregen):
                    todo.append((c.id, c.pregen["slogan_key"], *slogan_inputs(c.record, c)))
            for k in stats:
                stats[k] += st[k]
    stats["slogans_by_model"] = stats["slogans_deferred"] = 0
    budget = get_settings().pregen_llm_budget_s if llm_budget_s is None else llm_budget_s
    deadline = time.monotonic() + budget
    for n, (cid, key, rs, cs) in enumerate(todo):
        if time.monotonic() >= deadline or not complete.ready():
            stats["slogans_deferred"] = len(todo) - n
            break
        with session() as s:  # fresh copy of the stored dict (short read)
            c = s.get(Card, cid)
            pg = dict(c.pregen or {}) if c is not None else {}
        if pg.get("slogan_key") != key or not wants_model_slogan(pg):
            continue
        new = with_model_slogan(pg, rs, cs, complete)  # outside any transaction
        if new is pg:
            continue
        with session() as s:
            c = s.get(Card, cid)
            if c is not None and c.pregen and c.pregen.get("slogan_key") == key and c.pregen.get("slogan_by") == RULES:
                c.pregen = {**c.pregen, **{k: new[k] for k in ("slogan", "slogan_by", "slogan_tries", "llm_calls")}}
                stats["slogans_by_model"] += new["slogan_by"] == LOCAL
    stats["no_large_llm_pct"] = round(100 * stats["no_large_llm"] / stats["cards"], 1) if stats["cards"] else 0.0
    return stats


def business(rec, card) -> dict:
    """The stored business case. A card scored before pregeneration existed (until the next nightly run) gets
    the same rules computed on the spot: still no LLM, and counted in ``radar_pregen_cards{state="missing"}``."""
    stored = card.pregen or {}
    return stored.get("business") or business_case(rec, card)


CARD_VIEW = ("id", "solution_name", "problem_solved", "summary_pl", "maturity", "score", "decision", "assessment",
             "target_users", "provenance", "pregen")


def card_view(card, **override):
    """A detached copy of the card fields pregen reads, with overrides (the score stage's fresh assessment)."""
    from types import SimpleNamespace

    return SimpleNamespace(**{f: getattr(card, f, None) for f in CARD_VIEW} | override)


# One breaker per process: after a failed call (down, timeout) the model is skipped for the cooldown, so a hung
# llama.cpp costs one timeout, not one per card.
_slogan_open_until = [0.0]


def local_slogan() -> Callable[[str, str], dict] | None:
    """The small local model as a slogan writer, or None when it is not configured (then the rule slogan is used).
    Never a cloud model: this calls the llama.cpp server directly with the slogan grammar, and logs the call to
    ``llm_calls`` (purpose "slogan") so the cost panel counts it. The returned callable has ``ready()``: False
    while the circuit breaker is open (calls then raise at once, without touching the network)."""
    from radar.config import get_settings

    s = get_settings()
    if not (s.local_llm_url and s.pregen_local_slogan):
        return None
    import time

    from radar.llm.providers import LocalProvider, ProviderError
    from radar.llm.router import _record

    p = LocalProvider()
    p.grammar, p.json_mode, p.max_tokens, p.timeout = SLOGAN_GBNF, False, 80, min(p.timeout, s.pregen_slogan_timeout_s)
    cooldown = s.pregen_slogan_cooldown_s

    def ready() -> bool:
        return time.monotonic() >= _slogan_open_until[0]

    def complete(system: str, user: str) -> dict:
        if not ready():
            raise ProviderError("local slogan model in cooldown")
        t0 = time.perf_counter()
        try:
            out = p.complete_json(system, user)
        except Exception as e:
            _slogan_open_until[0] = time.monotonic() + cooldown
            _record(None, p.name, p.model, "slogan", False, (time.perf_counter() - t0) * 1000, str(e))
            raise
        _record(None, p.name, p.model, "slogan", True, (time.perf_counter() - t0) * 1000, usage=getattr(p, "last_usage", None))
        return out

    complete.ready = ready  # type: ignore[attr-defined]
    return complete
