"""HTTP API + operator UI.

/api/ingest/webhook/{source_id}  push sources over HTTP (HMAC-SHA256 in X-Radar-Signature when a secret is set)
/api/ingest/{source_id}/manual   manual submission of an innovation (zgłoszenie), same pipeline
/api/sources[/{id}/run]          list sources, trigger a pull
/api/cards[/{id}[/decision]]     operator queue: approve / reject
/api/stats                       stage counters (accepted = done + needs_review + skipped + in flight + DLQ)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, select, text

from radar import __version__
from radar.api.auth import operator
from radar.config import get_settings
from radar.db import migrate, session, wait_for_db
from radar.ingest import ingest_many
from radar.models import Card, RawRecord, Record, SourceState, StageRun
from radar.sources.base import Envelope, PushAdapter, SourceSpec
from radar.sources.push import verify_signature
from radar.sources.registry import active_sources, load_sources

STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_app):
    from radar.observability import setup_logging

    setup_logging()
    wait_for_db()
    migrate()  # T030: Alembic; idempotent, PostgreSQL advisory lock (the Helm migrate Job usually got there first)
    yield


app = FastAPI(title="Radar Innowacji", version=__version__, lifespan=lifespan)
from radar.api.explore import router as explore_router  # noqa: E402

from radar.api.insights import router as insights_router  # noqa: E402

app.include_router(explore_router)
app.include_router(insights_router)
from radar.api.deals import router as deals_router, v1 as partner_router  # noqa: E402

app.include_router(deals_router)
app.include_router(partner_router)
from radar.api.clusters import router as clusters_router  # noqa: E402

app.include_router(clusters_router)
from radar.api.guides import router as guides_router  # noqa: E402

app.include_router(guides_router)
from radar.observability import router as metrics_router, setup_logging  # noqa: E402

app.include_router(metrics_router)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "version": __version__}


@app.get("/readyz")
def readyz():
    with session() as s:
        s.execute(text("select 1"))
    return {"status": "ready"}


@app.get("/api/config")
def config():
    st = get_settings()
    return {"demo_mode": st.demo_mode, "llm_providers": st.llm_providers.split(","), "version": __version__}


# ---------------------------------------------------------------- sources
def _spec(source_id: str) -> SourceSpec:
    spec = load_sources().get(source_id)
    if spec is None or not spec.enabled:
        raise HTTPException(404, f"unknown or disabled source {source_id!r}")
    return spec


@app.get("/api/sources")
def sources():
    active = active_sources()
    with session() as s:
        states = {st.source_id: st for st in s.scalars(select(SourceState))}
        raw_counts = dict(s.execute(select(RawRecord.source_id, func.count()).group_by(RawRecord.source_id)).all())
    out = []
    for spec in load_sources().values():
        st = states.get(spec.id)
        out.append({
            "id": spec.id, "type": spec.type, "mode": spec.mode, "kind": spec.kind, "description": spec.description,
            "enabled": spec.enabled, "active": spec.id in active, "demo": spec.demo, "schedule_s": spec.schedule_s,
            "records": raw_counts.get(spec.id, 0),
            "last_run_at": st.last_run_at if st else None, "last_status": st.last_status if st else None,
            "last_error": st.last_error if st else None, "counters": st.counters if st else {},
        })
    return out


@app.post("/api/sources/{source_id}/run", status_code=202, dependencies=[Depends(operator)])
def run_source(source_id: str):
    from radar.pipeline.tasks import harvest

    spec = _spec(source_id)
    if spec.mode != "pull":
        raise HTTPException(400, "push source: send data to its webhook / topic instead")
    from kombu.exceptions import OperationalError

    try:
        res = harvest.apply_async((source_id,), queue="harvest", routing_key="harvest")
    except OperationalError as e:  # broker restarting: tell the caller to retry instead of a bare 500
        raise HTTPException(503, f"kolejka (broker) chwilowo niedostępna, spróbuj za chwilę: {e}") from e
    return {"task_id": res.id, "source_id": source_id}


@app.post("/api/ingest/webhook/{source_id}", status_code=202)
async def webhook(source_id: str, request: Request):
    spec = _spec(source_id)
    if spec.type != "webhook":
        raise HTTPException(400, f"source {source_id} is {spec.type!r}, not a webhook")
    body = await request.body()
    if not verify_signature(source_id, body, request.headers.get("x-radar-signature")):
        raise HTTPException(401, "bad signature")
    try:
        envelopes = PushAdapter(spec, "webhook").parse(body, dict(request.headers))
    except ValueError as e:
        raise HTTPException(400, f"cannot parse payload: {e}") from e
    return ingest_many(envelopes)


class ManualSubmission(BaseModel):
    title: str
    description: str
    institution: str | None = None
    institution_type: str | None = None  # szkoła | uczelnia | JST | inna instytucja publiczna
    region: str | None = None
    contact_role: str | None = None  # rola, nie dane osobowe (RODO)
    keywords: list[str] = []
    url: str | None = None


@app.post("/api/ingest/{source_id}/manual", status_code=202)
def manual(source_id: str, sub: ManualSubmission):
    spec = _spec(source_id)
    if spec.type != "webhook":
        raise HTTPException(400, "manual submissions go to a webhook-type source (e.g. `zgloszenia`)")
    from radar.ingest import content_hash

    payload = sub.model_dump()
    payload["submitted_at"] = datetime.now(timezone.utc).isoformat()
    env = Envelope(source_id=source_id, external_id="manual:" + content_hash(sub.model_dump())[:24],
                   payload=payload, received_via="upload")
    counts = ingest_many([env])
    with session() as s:
        raw = s.scalar(select(RawRecord).where(RawRecord.source_id == source_id, RawRecord.external_id == env.external_id))
        return {**counts, "raw_id": raw.id, "track": f"/api/submissions/{raw.id}"}


@app.get("/api/submissions/{raw_id}")
def submission_status(raw_id: int):
    """Where a submission is in the pipeline (stages done, Basal labels, card when ready)."""
    order = ["normalize", "resolve_org", "dedup", "gate", "link", "extract", "maturity", "score"]
    with session() as s:
        raw = s.get(RawRecord, raw_id)
        if raw is None:
            raise HTTPException(404)
        runs = {r.stage: r for r in s.scalars(select(StageRun).where(StageRun.raw_id == raw_id))}
        rec = s.scalar(select(Record).where(Record.raw_id == raw_id))
        card = rec.card if rec else None
        return {"raw_id": raw_id, "source_id": raw.source_id, "received_at": raw.fetched_at,
                "stages": [{"stage": st, "status": runs[st].outcome if st in runs else "pending",
                            "detail": (runs[st].detail if st in runs else None)} for st in order],
                "record_status": rec.status if rec else None,
                "labels": {a: getattr(rec, a) for a in ("sector", "innovation_type", "institution_type", "voivodeship")} if rec else None,
                "review_reasons": rec.review_reasons if rec else [],
                "card_id": card.id if card and card.score is not None else None}


# ---------------------------------------------------------------- operator
def card_dict(c: Card, full: bool = False) -> dict:
    r = c.record
    d = {
        "id": c.id, "decision": c.decision, "solution_name": c.solution_name, "summary_pl": c.summary_pl,
        "innovation_type": c.innovation_type, "maturity": c.maturity, "hidden": c.hidden, "missing": c.missing,
        "target_users": c.target_users, "provider": (c.provenance or {}).get("provider"),
        "score": c.score, "likes": c.likes, "synthetic": bool((r.extra or {}).get("synthetic")),
        "record": {"id": r.id, "source_id": r.source_id, "kind": r.kind, "title": r.title, "year": r.year,
                   "doi": r.doi, "url": r.url, "affiliations": r.affiliations, "region": r.region,
                   "voivodeship": r.voivodeship, "sector": r.sector, "tech_area": r.tech_area},
    }
    if full:
        d.update(problem_solved=c.problem_solved, what_is_new=c.what_is_new, evidence=c.evidence,
                 reasoning=c.reasoning, provenance=c.provenance, decision_note=c.decision_note,
                 decided_at=c.decided_at, assessment=c.assessment, brief=c.brief, basal=r.basal)
        from radar.business import business_case

        d["business"] = business_case(r, c) if c.maturity else None
        if d["business"]:
            from sqlalchemy.orm import object_session

            from radar.investor import signals

            d["investor"] = signals(object_session(c), r, c, d["business"])
        d["record"].update(abstract=r.abstract, authors=r.authors, keywords=r.keywords, licence=r.licence,
                           amounts=r.amounts, extra=r.extra)
    return d


@app.get("/api/cards")
def cards(decision: str | None = None, maturity: str | None = None, limit: int = 100, offset: int = 0):
    with session() as s:
        q = select(Card).order_by(Card.id.desc()).limit(min(limit, 500)).offset(offset)
        if decision:
            q = q.where(Card.decision == decision)
        if maturity:
            q = q.where(Card.maturity == maturity)
        return [card_dict(c) for c in s.scalars(q)]


@app.get("/api/cards/{card_id}")
def card(card_id: int):
    with session() as s:
        c = s.get(Card, card_id)
        if c is None:
            raise HTTPException(404)
        return card_dict(c, full=True)


class Decision(BaseModel):
    decision: Literal["approved", "rejected", "pending"]
    note: str | None = None


@app.post("/api/cards/{card_id}/decision", dependencies=[Depends(operator)])
def decide(card_id: int, d: Decision):
    with session() as s:
        c = s.get(Card, card_id)
        if c is None:
            raise HTTPException(404)
        c.decision, c.decision_note, c.decided_at = d.decision, d.note, datetime.now(timezone.utc)
        return card_dict(c)


@app.get("/api/review")
def review(limit: int = 100):
    with session() as s:
        q = select(Record).where(Record.status == "needs_review").order_by(Record.id.desc()).limit(limit)
        return [{"id": r.id, "source_id": r.source_id, "title": r.title, "reasons": r.review_reasons} for r in s.scalars(q)]


@app.get("/api/stats")
def stats():
    with session() as s:
        records = dict(s.execute(select(Record.status, func.count()).group_by(Record.status)).all())
        stages: dict = {}
        for stage, outcome, n in s.execute(select(StageRun.stage, StageRun.outcome, func.count())
                                           .group_by(StageRun.stage, StageRun.outcome)):
            stages.setdefault(stage, {})[outcome] = n
        raw = dict(s.execute(select(RawRecord.received_via, func.count()).group_by(RawRecord.received_via)).all())
        decisions = dict(s.execute(select(Card.decision, func.count()).group_by(Card.decision)).all())
    return {"raw_by_transport": raw, "records_by_status": records, "stages": stages, "cards_by_decision": decisions}


@app.get("/")
def index():
    # no-cache: the single-page UI changes with every deploy; browsers must revalidate
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


@app.middleware("http")
async def _revalidate_static(request: Request, call_next):
    """UI assets change with every deploy: browsers revalidate (ETag makes it a cheap 304)."""
    resp = await call_next(request)
    if request.url.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


app.mount("/static", StaticFiles(directory=STATIC), name="static")
