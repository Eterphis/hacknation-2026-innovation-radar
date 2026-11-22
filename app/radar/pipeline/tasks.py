"""Pipeline stages (pipeline-design §10, §16):

harvest -> normalize -> resolve_org -> dedup -> link -> extract -> maturity -> score

Messages carry only (raw_id, content_hash). Each stage:
1. checks StageRun for (raw_id, stage, hash) — already done means redelivery, return;
2. does its work in one DB transaction and writes its StageRun row in the same transaction;
3. enqueues the next stage.
If step 3 is lost (crash between commit and publish), `radar reconcile` finds records whose last StageRun
is not terminal and re-enqueues them. Nothing is lost silently; counters come from StageRun.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from celery import signals

from sqlalchemy import select

from radar.db import session
from radar.models import Card, RawRecord, Record, SourceState, StageRun
from radar.pipeline import extract as ex
from radar.pipeline.celery_app import app
from radar.pipeline.normalize import apply_mapping, norm_title, programme_key, quality_gate, same_programme
from radar.sources.registry import connector, get_source

log = logging.getLogger(__name__)
RETRY = dict(bind=True, autoretry_for=(Exception,), retry_backoff=5, retry_backoff_max=300, max_retries=3,
             dont_autoretry_for=(KeyError, ValueError))


def _score_limits() -> dict:
    """`score` limits follow the agent's LLM budget: the budget ends first (rules take over), the soft limit is a
    safety net the agent also catches, and a task that still hits it is not retried from scratch three times."""
    from celery.exceptions import SoftTimeLimitExceeded

    from radar.config import get_settings

    budget = get_settings().agent_budget_s
    return {**RETRY, "soft_time_limit": budget + 60, "time_limit": budget + 120,
            "dont_autoretry_for": (*RETRY["dont_autoretry_for"], SoftTimeLimitExceeded)}


def _done(s, raw_id: int, stage: str, h: str) -> bool:
    return s.scalar(select(StageRun.id).where(StageRun.raw_id == raw_id, StageRun.stage == stage,
                                              StageRun.content_hash == h)) is not None


# Stage wall time: a stack per thread, because eager mode (tests, `radar demo`) runs the next stage inside this one.
_clock = threading.local()


@signals.task_prerun.connect
def _start_clock(task_id=None, **_):
    _clock.__dict__.setdefault("stack", []).append(time.perf_counter())


@signals.task_postrun.connect
def _stop_clock(task_id=None, **_):
    st = _clock.__dict__.get("stack")
    if st:
        st.pop()


def _elapsed_ms() -> float | None:
    st = _clock.__dict__.get("stack")
    return round((time.perf_counter() - st[-1]) * 1000, 1) if st else None


def _mark(s, raw_id: int, stage: str, h: str, outcome: str = "ok", detail: str | None = None) -> None:
    ms = _elapsed_ms()
    s.add(StageRun(raw_id=raw_id, stage=stage, content_hash=h, outcome=outcome, detail=detail, duration_ms=ms))
    log.info("stage %s %s", stage, outcome, extra={"raw_id": raw_id, "stage": stage, "outcome": outcome, "duration_ms": ms})


def _next(stage: str, raw_id: int, h: str, priority: int | None = None) -> None:
    kw = {"priority": priority} if priority is not None else {}
    globals()[stage].apply_async((raw_id, h), queue=stage, routing_key=stage, **kw)


def _priority(rec: Record) -> int:
    """Basal priority 0..1 -> RabbitMQ priority 0..9 (LLM queues have x-max-priority)."""
    return int(round(9 * float((rec.basal or {}).get("priority") or 0)))


def enqueue_normalize(raw_id: int, h: str) -> None:
    _next("normalize", raw_id, h)


# ---------------------------------------------------------------- harvest
@app.task(**RETRY)
def harvest(self, source_id: str) -> dict:
    from radar.ingest import ingest_many

    spec = get_source(source_id)
    if spec.mode != "pull":
        raise ValueError(f"{source_id} is a push source; it is fed by its consumer or webhook")
    with session() as s:
        st = s.get(SourceState, source_id) or SourceState(source_id=source_id, counters={})
        s.add(st)
        cursor = st.cursor
    totals = {"accepted": 0, "new": 0, "updated": 0, "unchanged": 0, "deleted": 0, "pages": 0}
    try:
        for page in connector(spec).fetch(cursor):
            counts = ingest_many(page.items)
            for k, v in counts.items():
                totals[k] += v
            totals["pages"] += 1
            # checkpoint after every page: a crash resumes from here
            with session() as s:
                st = s.get(SourceState, source_id)
                if page.next_cursor:
                    st.cursor = page.next_cursor
                st.counters = totals
        status, err = "ok", None
    except Exception as e:
        status, err = "failed", f"{type(e).__name__}: {e}"[:2000]
        raise
    finally:
        with session() as s:
            st = s.get(SourceState, source_id)
            st.last_run_at, st.last_status, st.last_error = datetime.now(timezone.utc), status, err
            st.counters = totals
    log.info("harvest %s: %s", source_id, totals, extra={"source_id": source_id, "stage": "harvest"})
    return totals


# ---------------------------------------------------------------- normalize
@app.task(**RETRY)
def normalize(self, raw_id: int, h: str) -> str:
    with session() as s:
        if _done(s, raw_id, "normalize", h):
            return "duplicate-delivery"
        raw = s.get(RawRecord, raw_id)
        rec = s.scalar(select(Record).where(Record.raw_id == raw_id)) or Record(raw_id=raw_id, source_id=raw.source_id)
        s.add(rec)
        if raw.status == "deleted":
            rec.status = "deleted"
            _mark(s, raw_id, "normalize", h, "skipped", "usunięty w źródle")
            return "deleted"
        spec = get_source(raw.source_id)
        fields, extra = apply_mapping(spec, raw.payload)
        for k, v in fields.items():
            setattr(rec, k, v)
        rec.amounts = {k: v for k, v in extra.items() if k.startswith("amount")}
        rec.extra = {k: v for k, v in extra.items() if not k.startswith("amount")}
        rec.cluster_id = None
        reasons = quality_gate(fields, int(spec.options.get("min_abstract_chars", 200)))
        rec.review_reasons = reasons
        rec.status = "needs_review" if reasons else "normalized"
        _mark(s, raw_id, "normalize", h, "needs_review" if reasons else "ok", "; ".join(reasons) or None)
    if not reasons:
        _next("resolve_org", raw_id, h)
    return rec.status


# ---------------------------------------------------------------- resolve_org
@app.task(**RETRY)
def resolve_org(self, raw_id: int, h: str) -> str:
    """T023: match affiliations against the organisation registry (RAD-on institutions; radar.orgs), cascade
    id -> alias -> acronym -> contains -> fuzzy with confidence. A sure match gives Basal the institution type,
    public/private and the voivodeship (when the record has no region). No registry yet = pass-through."""
    from radar import orgs

    with session() as s:
        if _done(s, raw_id, "resolve_org", h):
            return "duplicate-delivery"
        rec = s.scalar(select(Record).where(Record.raw_id == raw_id))
        matcher = orgs.ensure_registry(s)
        if matcher is None or not rec.affiliations:
            _mark(s, raw_id, "resolve_org", h, "ok", "brak rejestru organizacji" if matcher is None else "brak afiliacji")
            outcome = "pass-through"
        else:
            results = orgs.resolve(matcher, rec.affiliations, (rec.extra or {}).get("organizations"))
            facts = orgs.summary(results)
            extra = {**(rec.extra or {}), "orgs": results}
            if facts:
                extra["org_id"] = facts.get("org_id")
                extra["is_public"] = facts.get("is_public")
                # a type declared in a submission form stays; otherwise the registry is the sure source
                if facts.get("institution_type") and not extra.get("institution_type"):
                    extra["institution_type"] = facts["institution_type"]
                if facts.get("voivodeship") and not rec.region:
                    rec.region = facts["voivodeship"]
            rec.extra = extra
            n_ok = sum(1 for r in results if r["accepted"])
            outcome = f"{n_ok}/{len(results)} dopasowanych"
            _mark(s, raw_id, "resolve_org", h, "ok", outcome)
    _next("dedup", raw_id, h)
    return outcome


# ---------------------------------------------------------------- dedup
def completeness(rec: Record) -> float:
    """How much a record tells about the idea. Within a cluster the fullest record is canonical (T025), so a
    richer copy that arrives later (DOI, abstract, organisations, amounts) replaces a thin first one."""
    text = min(len(rec.abstract or ""), 2000) / 200          # up to 10 points for the description
    return (text + (3 if rec.doi else 0) + min(len(rec.affiliations or []), 5) + min(len(rec.authors or []), 3) * 0.5
            + min(len(rec.keywords or []), 6) * 0.5 + (1 if rec.year else 0) + (1 if rec.url else 0)
            + (1 if rec.region else 0) + (2 if any(v for v in (rec.amounts or {}).values()) else 0))


def _fuller(a: Record, b: Record) -> bool:
    """a should be canonical instead of b: more complete, ties go to the older record (stable result)."""
    ca, cb = completeness(a), completeness(b)
    return ca > cb or (ca == cb and a.id < b.id)


def _find_match(s, rec: Record, group_by_title: bool) -> tuple[Record | None, str | None]:
    """Canonical record (not a duplicate) this one duplicates. Layers 2-3 of §16: same DOI, or same normalized
    title + year; sources with `group_by_title` (Kohesio: one programme, many beneficiaries) group projects of
    the same programme (normalize.programme_key: phases, places, scope removed) whatever the year.
    Layers 4-5 (embeddings) stay in the graph as possible_duplicate."""
    live = (Record.id != rec.id, Record.status.notin_(("duplicate", "deleted")))
    if rec.doi:
        m = s.scalar(select(Record).where(Record.doi == rec.doi, *live).order_by(Record.id))
        if m is not None:
            return m, f"ten sam DOI {rec.doi}"
    nt = norm_title(rec.title)
    if not nt:
        return None, None
    if group_by_title:
        pk = programme_key(rec.title)
        prefix = (rec.title or "")[:6].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        for other in s.scalars(select(Record).where(Record.source_id == rec.source_id, *live,
                                                    Record.title.ilike(prefix + "%", escape="\\")).order_by(Record.id)):
            if norm_title(other.title) == nt or same_programme(pk, programme_key(other.title)):
                return other, f"ten sam program „{pk}” w {rec.source_id} (grupa projektów)"
    if rec.year:
        for other in s.scalars(select(Record).where(Record.year.between(rec.year - 1, rec.year + 1), *live,
                                                    Record.kind == rec.kind).order_by(Record.id)):
            if norm_title(other.title) == nt:
                return other, f"ten sam tytuł i rok ({other.source_id})"
    return None, None


def _group_size(s, cluster_id: int) -> int:
    return len(s.scalars(select(Record.id).where(Record.cluster_id == cluster_id)).all())


@app.task(**RETRY)
def dedup(self, raw_id: int, h: str) -> str:
    """Cluster duplicates; the fullest record of a cluster is canonical and goes on, the others stop as
    `duplicate` pointing at it (cluster_id = canonical id). A fuller newcomer takes over: the old canonical is
    demoted and its cluster repointed, whatever order the sources were harvested in."""
    with session() as s:
        if _done(s, raw_id, "dedup", h):
            return "duplicate-delivery"
        rec = s.scalar(select(Record).where(Record.raw_id == raw_id))
        group = bool(get_source(rec.source_id).options.get("group_by_title", False))
        match, reason = _find_match(s, rec, group)
        if match is not None and not _fuller(rec, match):
            rec.status = "duplicate"
            rec.cluster_id = match.cluster_id or match.id
            rec.review_reasons = [f"duplikat rekordu #{match.id}: {reason}"]
            s.flush()
            n = _group_size(s, rec.cluster_id)
            match.extra = {**(match.extra or {}), "cluster_size": n}
            _mark(s, raw_id, "dedup", h, "skipped", reason)
            return "duplicate"
        rec.cluster_id = rec.id
        if match is not None:
            old = match.cluster_id or match.id
            for member in s.scalars(select(Record).where(Record.cluster_id == old)):
                member.cluster_id = rec.id
                member.review_reasons = [r.replace(f"duplikat rekordu #{match.id}", f"duplikat rekordu #{rec.id}")
                                         for r in member.review_reasons or []]
            match.cluster_id = rec.id
            match.status = "duplicate"
            match.review_reasons = [f"duplikat rekordu #{rec.id} (pełniejszy opis): {reason}"]
            if match.card is not None:
                match.card.hidden = True
            # terminal marker: reconcile does not re-enqueue it and later stages leave it alone
            _mark(s, match.raw_id, "superseded", match.raw.content_hash, "skipped", f"zastąpiony przez #{rec.id}")
            s.flush()
            rec.extra = {**(rec.extra or {}), "cluster_size": _group_size(s, rec.id)}
            log.info("dedup: #%s replaces #%s as canonical (%s)", rec.id, match.id, reason)
        _mark(s, raw_id, "dedup", h, "ok", f"zastępuje #{match.id} jako pełniejszy: {reason}" if match else None)
    _next("gate", raw_id, h)
    return "canonical" if match is not None else "ok"


# ---------------------------------------------------------------- gate (Basal)
@app.task(**RETRY)
def gate(self, raw_id: int, h: str) -> str:
    """Basal before any LLM: reject / hold / accept with reasons, multi-axis labels, priority. No LLM."""
    from radar.basal.classifier import classify, mask_pii

    with session() as s:
        if _done(s, raw_id, "gate", h):
            return "duplicate-delivery"
        rec = s.scalar(select(Record).where(Record.raw_id == raw_id))
        if rec.status == "duplicate":  # a fuller record took over the cluster meanwhile
            return "superseded"
        spec = get_source(rec.source_id)
        b = classify(title=rec.title, abstract=rec.abstract, keywords=rec.keywords, affiliations=rec.affiliations,
                     region=rec.region, kind=rec.kind, amounts=rec.amounts,
                     declared_institution=(rec.extra or {}).get("institution_type"),
                     min_chars=int(spec.options.get("min_abstract_chars", 200)))
        rec.basal = b
        for axis in ("sector", "tech_area", "innovation_type", "institution_type", "voivodeship", "cost_level"):
            setattr(rec, axis, b[axis]["value"])
        rec.priority = b["priority"]
        if b["pii"]:
            rec.abstract, _ = mask_pii(rec.abstract)
            rec.title, _ = mask_pii(rec.title)
        if b["decision"] == "reject":
            rec.status, rec.review_reasons = "rejected", b["reject_reasons"]
            _mark(s, raw_id, "gate", h, "skipped", "; ".join(b["reject_reasons"])[:2000])
            return "rejected"
        if b["decision"] == "hold":
            rec.status, rec.review_reasons = "needs_review", ["Basal: " + r for r in b["hold_reasons"]]
            _mark(s, raw_id, "gate", h, "needs_review", "; ".join(b["hold_reasons"]))
            return "hold"
        _mark(s, raw_id, "gate", h, "ok", b["routing_key"])
        prio = _priority(rec)
    _next("link", raw_id, h, prio)
    return "accept"


# ---------------------------------------------------------------- link
@app.task(**RETRY)
def link(self, raw_id: int, h: str) -> str:
    """TODO(T024): evidence chain publication <-> project <-> patent <-> Kohesio investment by org_id,
    OpenAIRE relations and description similarity. Pass-through for now."""
    with session() as s:
        if _done(s, raw_id, "link", h):
            return "duplicate-delivery"
        _mark(s, raw_id, "link", h, "ok", "pass-through (łańcuch dowodów: T024)")
        prio = _priority(s.scalar(select(Record).where(Record.raw_id == raw_id)))
    _next("extract", raw_id, h, prio)
    return "ok"


# ---------------------------------------------------------------- extract
@app.task(**RETRY)
def extract(self, raw_id: int, h: str) -> str:
    """LLM extraction. The pre-filter that used to live here is now Basal (`gate`)."""
    with session() as s:
        if _done(s, raw_id, "extract", h):
            return "duplicate-delivery"
        rec = s.scalar(select(Record).where(Record.raw_id == raw_id))
        if rec.status == "duplicate":
            return "superseded"
        text = ex.source_text(rec.title, rec.abstract, rec.keywords or [])

    out, errors, prov = ex.extract(text)  # outside the transaction: the LLM call can take a while

    with session() as s:
        rec = s.scalar(select(Record).where(Record.raw_id == raw_id))
        if out is None:
            rec.status, rec.review_reasons = "needs_review", errors
            _mark(s, raw_id, "extract", h, "needs_review", "; ".join(errors)[:2000])
            return "needs_review"
        if out.get("is_innovation") == "nie":
            rec.status, rec.review_reasons = "not_innovation", [f"LLM: nie innowacja — „{out.get('is_innovation_quote', '')}”"]
            _mark(s, raw_id, "extract", h, "skipped", "llm: nie")
            return "not_innovation"
        card = s.scalar(select(Card).where(Card.record_id == rec.id)) or Card(record_id=rec.id)
        s.add(card)
        val = lambda f: (out.get(f) or {}).get("value")  # noqa: E731
        card.solution_name, card.problem_solved, card.what_is_new = val("solution_name"), val("problem_solved"), val("what_is_new")
        card.target_users = val("target_users") or []
        # A real model's type (with a verified quote) wins over Basal; the offline heuristic never overrides Basal.
        # ...but when Basal had no confident label, any validated extraction value is better than none.
        llm_type = val("innovation_type") if (prov.get("provider") != "mock" or rec.innovation_type is None) else None
        if llm_type in ex.INNOVATION_TYPES:
            rec.innovation_type = {"społeczna": "spoleczna", "usługowa": "uslugowa"}.get(llm_type, llm_type)
        card.innovation_type = rec.innovation_type or val("innovation_type")
        card.summary_pl = out.get("summary_pl")
        card.evidence = {f: {"quote": (out.get(f) or {}).get("quote"), "confidence": (out.get(f) or {}).get("confidence")}
                         for f in ex.QUOTED_FIELDS}
        card.provenance = prov
        card.decision = "pending" if card.decision is None else card.decision
        rec.status = "extracted"
        _mark(s, raw_id, "extract", h, "ok", f"{prov.get('provider')}/{prov.get('model')}")
        prio = _priority(rec)
    _next("maturity", raw_id, h, prio)
    return "ok"


# ---------------------------------------------------------------- maturity
LEVELS = ["exploring", "tech_ready", "business_ready", "market_ready"]
NEXT_EVIDENCE = {
    "exploring": "patent albo opis prototypu / pilotażu",
    "tech_ready": "projekt wdrożeniowy lub inwestycyjny (Kohesio, NCBR), spin-off w KRS",
    "business_ready": "wdrożenie w więcej niż jednej instytucji",
    "market_ready": None,
}


def maturity_for(rec: Record) -> tuple[str, str]:
    """Rules from pipeline-design §8. TODO(T024): use the whole evidence chain of the cluster, not one record."""
    text = f"{rec.title} {rec.abstract}".lower()
    if rec.kind == "patent":
        return "tech_ready", "patent"
    if rec.kind in ("project", "solution") and rec.extra.get("implementation"):
        return "business_ready", "projekt wdrożeniowy / inwestycyjny"
    if any(w in text for w in ("pilotaż", "pilotaz", "prototyp", "prototype", "pilot ", "demonstrator")):
        return "tech_ready", "opis prototypu lub pilotażu"
    hint = (rec.basal or {}).get("maturity_hint") or {}
    if rec.kind == "solution" and hint.get("value") in ("business_ready", "market_ready") and hint.get("confidence", 0) >= 0.6:
        return hint["value"], "zgłoszenie opisuje działające wdrożenie (" + ", ".join(hint.get("evidence", [])[:2]) + ")"
    return "exploring", "publikacja lub projekt badawczy"


@app.task(**RETRY)
def maturity(self, raw_id: int, h: str) -> str:
    with session() as s:
        if _done(s, raw_id, "maturity", h):
            return "duplicate-delivery"
        rec = s.scalar(select(Record).where(Record.raw_id == raw_id))
        if rec.status == "duplicate":
            return "superseded"
        card = rec.card
        level, why = maturity_for(rec)
        card.maturity = level
        nxt = NEXT_EVIDENCE[level]
        card.missing = [nxt] if nxt else []
        card.hidden = LEVELS.index(level) >= 1 and not rec.extra.get("deployed_elsewhere")
        card.reasoning = build_reasoning(rec, card, why)
        rec.status = "ready"
        _mark(s, raw_id, "maturity", h, "ok", level)
        prio = _priority(rec)
    _next("score", raw_id, h, prio)
    return level


def build_reasoning(rec: Record, card: Card, why: str) -> list[dict]:
    """Uzasadnienie w układzie decyzji urzędowej (D-008 / I-011): ustalenia -> kryteria -> ocena -> ograniczenia."""
    ev = card.evidence or {}
    findings = [f"Źródło: {rec.source_id}" + (f", DOI {rec.doi}" if rec.doi else "") + (f", rok {rec.year}" if rec.year else "")]
    for f, label in [("problem_solved", "Problem"), ("what_is_new", "Co nowego"), ("target_users", "Dla kogo")]:
        q = (ev.get(f) or {}).get("quote")
        if q:
            findings.append(f"{label}: „{q}”")
    return [
        {"step": "Co ustalono", "items": findings},
        {"step": "Kryteria", "items": ["dojrzałość z dowodów (§8 projektu potoku)", "typ innowacji z listy",
                                       "cytat ze źródła dla każdego pola"]},
        {"step": "Ocena", "items": [f"Poziom dojrzałości: {card.maturity} (dowód: {why})",
                                    f"Typ: {card.innovation_type or 'nieustalony'}"]},
        {"step": "Czego brakuje", "items": card.missing or ["—"]},
        {"step": "Ograniczenia", "items": [f"Ekstrakcja: {card.provenance.get('provider')}/{card.provenance.get('model')}",
                                          "Rozpoznanie organizacji i łańcuch dowodów jeszcze niewdrożone (T023, T024)"]},
    ]


# ---------------------------------------------------------------- score
@app.task(**_score_limits())
def score(self, raw_id: int, h: str) -> str:
    """Graph index (embedding + similarity edges) -> implementation agent with tools -> Basal recheck ->
    weighted criteria score -> one-page brief for the reels feed. Recipient matching from registries: T026."""
    from radar.basal.graph import index_record
    from radar.pipeline.assess import assess, brief

    with session() as s:  # graph index first, committed: edges are rebuilt idempotently on redelivery
        if _done(s, raw_id, "score", h):
            return "duplicate-delivery"
        index_record(s, s.scalar(select(Record).where(Record.raw_id == raw_id)))
    # The agent may spend minutes on a CPU model: this session only reads (tools), LLM calls are logged in their
    # own short sessions, so nothing holds a write lock or a write transaction while the model works.
    with session() as s:
        if _done(s, raw_id, "score", h):
            return "duplicate-delivery"
        rec = s.scalar(select(Record).where(Record.raw_id == raw_id))
        a = assess(s, rec, rec.card)
        b = brief(rec, rec.card, a)
        s.rollback()  # read-only by contract: drop anything a tool might have touched
    # Short write transaction; re-check, because a redelivered copy may have finished while the model worked.
    with session() as s:
        if _done(s, raw_id, "score", h):
            return "duplicate-delivery"
        card = s.scalar(select(Record).where(Record.raw_id == raw_id)).card
        card.assessment, card.score, card.brief = a, a["total"], b
        card.reasoning = (card.reasoning or [])[:3] + [
            {"step": "Ocena wg kryteriów", "items": [f"{k}: {v['score']}/5 — {v['why']}" for k, v in a["scores"].items()]
             + [f"Wynik łączny: {a['total']}/100"]},
            {"step": "Rekomendowana ścieżka", "items": [f"{p['path']}: {p['why']}" for p in a["paths"]]},
            {"step": "Co przemawia przeciw", "items": [f"{x['point']} ({x['severity']}; {', '.join(x['cite'])})" for x in a.get("against") or []] or ["—"]},
            {"step": "Ryzyka i mitygacje", "items": [f"{r['risk']} → {r['mitigation']} ({r['owner']})" for r in a["risks"]] or ["—"]},
            {"step": "Mierniki skuteczności", "items": a["metrics"]},
        ] + (card.reasoning or [])[3:]
        _mark(s, raw_id, "score", h, "ok", f"{a['total']} ({a['by']})")
    return "ok"


# ---------------------------------------------------------------- watchlists
@app.task
def notify_watchlists() -> dict:
    from radar.api.deals import notify_watchlists as run

    return run()


# ---------------------------------------------------------------- reassess
@app.task(bind=True, max_retries=2)
def reassess(self) -> int:
    """Re-index and re-assess every ready card. Novelty, recipients and regional gaps depend on the whole
    collection, so cards scored early go stale as new ideas arrive. Runs daily from beat and after `radar demo`."""
    from radar.basal.graph import index_record
    from radar.pipeline.assess import assess, brief

    with session() as s:
        ids = s.scalars(select(Record.id).where(Record.status == "ready")).all()
        for rid in ids:
            index_record(s, s.get(Record, rid))
        s.flush()
        for rid in ids:
            rec = s.get(Record, rid)
            if rec.card is None:
                continue
            a = assess(s, rec, rec.card)
            rec.card.assessment, rec.card.score, rec.card.brief = a, a["total"], brief(rec, rec.card, a)
    return len(ids)


# ---------------------------------------------------------------- reconcile
def reconcile_all() -> int:
    """Re-enqueue records whose pipeline stopped mid-way (publish lost after commit). Safe: stages are idempotent."""
    order = ["normalize", "resolve_org", "dedup", "gate", "link", "extract", "maturity", "score"]
    todo = []
    with session() as s:
        raws = s.execute(select(RawRecord.id, RawRecord.content_hash).where(RawRecord.status != "deleted")).all()
        for raw_id, h in raws:
            runs = {r.stage: r.outcome for r in s.scalars(select(StageRun).where(StageRun.raw_id == raw_id,
                                                                                  StageRun.content_hash == h))}
            if any(o in ("needs_review", "skipped") for o in runs.values()) or "score" in runs:
                continue
            nxt = next((st for st in order if st not in runs), None)
            if nxt:
                todo.append((nxt, raw_id, h))
    for stage, raw_id, h in todo:
        _next(stage, raw_id, h)
    return len(todo)


__all__ = ["harvest", "normalize", "resolve_org", "dedup", "gate", "link", "extract", "maturity", "score", "notify_watchlists",
           "reconcile_all"]
