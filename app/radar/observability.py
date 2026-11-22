"""Observability: Prometheus metrics computed from the database (single source of truth across api / workers /
consumers, no multiprocess registry needed) + RabbitMQ queue depths from the management API + JSON logs.

GET /metrics  (text/plain; version=0.0.4)
"""

from __future__ import annotations

import json
import logging
import os
import time
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from sqlalchemy import case, func, select

from radar.config import get_settings
from radar.db import session
from radar.models import Card, LlmCall, RawRecord, Record, SourceState, StageRun

STAGE_BUCKETS_S = (0.01, 0.05, 0.1, 0.5, 1, 5, 15, 60, 300)
LLM_BUCKETS_S = (0.5, 1, 2, 5, 10, 30, 60, 120, 300)

router = APIRouter()
_STARTED = time.time()


def _lbl(**kw) -> str:
    return "{" + ",".join(f'{k}="{str(v).replace(chr(34), "")}"' for k, v in kw.items()) + "}"


def _rabbit_queues() -> list[dict]:
    """Queue depths via the RabbitMQ management API (port 15672), derived from RADAR_BROKER_URL."""
    url = get_settings().broker_url
    if not url.startswith("amqp"):
        return []
    u = urlparse(url)
    mgmt = os.environ.get("RADAR_RABBIT_MGMT_URL") or f"http://{u.hostname}:15672"
    try:
        r = httpx.get(f"{mgmt}/api/queues", auth=(u.username or "guest", u.password or "guest"), timeout=2.0)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


def _histogram(s, out: list[str], name: str, help_: str, col_ms, group_cols: list, where, buckets: tuple) -> None:
    """Prometheus histogram computed in one SQL query: cumulative bucket counts, sum and count per label set."""
    q = select(*group_cols, func.count(), func.coalesce(func.sum(col_ms), 0),
               *[func.sum(case((col_ms <= b * 1000, 1), else_=0)) for b in buckets]).where(where).group_by(*group_cols)
    out.append(f"# HELP {name} {help_}")
    out.append(f"# TYPE {name} histogram")
    keys = [c.key for c in group_cols]
    for row in s.execute(q):
        labels = dict(zip(keys, row[:len(keys)]))
        n, total = row[len(keys)], row[len(keys) + 1]
        for b, c in zip(buckets, row[len(keys) + 2:]):
            out.append(f"{name}_bucket{_lbl(**labels, le=b)} {c or 0}")
        out.append(f"{name}_bucket{_lbl(**labels, le='+Inf')} {n}")
        out.append(f"{name}_sum{_lbl(**labels)} {round((total or 0) / 1000, 3)}")
        out.append(f"{name}_count{_lbl(**labels)} {n}")


def _prices() -> dict:
    try:
        return json.loads(get_settings().llm_prices or "{}")
    except ValueError:
        return {}


CLOUD_NAMES = {"anthropic", "openai"}
LOCAL_NAMES = {"local"}


def llm_path(card) -> str:
    """How a card was produced: "cloud" if a large cloud model wrote any part of it (extraction or the assessment
    agent), "local" if only the small local model did, else "rules" (Basal, rule agent, mock heuristic)."""
    used = {(card.provenance or {}).get("provider"), (((card.assessment or {}).get("agent") or {}).get("provider"))}
    if used & CLOUD_NAMES:
        return "cloud"
    if used & LOCAL_NAMES:
        return "local"
    return "rules"


def _cost_rule_metrics(s, emit) -> None:
    """Cost rule of #13: how many cards never touched a large cloud model, and whether pregen is current."""
    from radar.pregen import VERSION

    paths = {"rules": 0, "local": 0, "cloud": 0}
    pregen = {"current": 0, "outdated": 0, "missing": 0}
    slogans: dict[str, int] = {}
    for card in s.scalars(select(Card).where(Card.score.is_not(None))):
        paths[llm_path(card)] += 1
        pg = card.pregen
        state = "missing" if not pg else "current" if pg.get("version") == VERSION else "outdated"
        pregen[state] += 1
        if pg:
            slogans[pg.get("slogan_by") or "?"] = slogans.get(pg.get("slogan_by") or "?", 0) + 1
    total = sum(paths.values())
    emit("radar_cards_by_llm_path", "Scored cards by the most expensive model that wrote them (rules|local|cloud)",
         "gauge", [({"path": p}, n) for p, n in paths.items()])
    emit("radar_cards_without_large_llm_ratio", "Share of scored cards never touched by a large cloud model (target > 0.9)",
         "gauge", [({}, round((paths["rules"] + paths["local"]) / total, 4) if total else 1)])
    emit("radar_pregen_cards", "Scored cards by pregenerated content state", "gauge",
         [({"state": k}, n) for k, n in pregen.items()])
    emit("radar_pregen_slogans", "Pregenerated slogans by author (reguły | local-llm)", "gauge",
         [({"by": k}, n) for k, n in slogans.items()])
    emit("radar_llm_cloud_allowed", "1 when RADAR_LLM_ALLOW_CLOUD is set (cloud models may join the chain)", "gauge",
         [({}, 1 if get_settings().llm_allow_cloud else 0)])


@router.get("/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    out: list[str] = []

    def emit(name: str, help_: str, kind: str, rows: list[tuple[dict, float]]):
        out.append(f"# HELP {name} {help_}")
        out.append(f"# TYPE {name} {kind}")
        for labels, v in rows:
            out.append(f"{name}{_lbl(**labels) if labels else ''} {v}")

    with session() as s:
        emit("radar_stage_runs_total", "Pipeline stage executions by outcome", "counter",
             [({"stage": st, "outcome": oc}, n) for st, oc, n in
              s.execute(select(StageRun.stage, StageRun.outcome, func.count()).group_by(StageRun.stage, StageRun.outcome))])
        _histogram(s, out, "radar_stage_duration_seconds", "Wall time of a pipeline stage (incl. LLM calls in extract/score)",
                   StageRun.duration_ms, [StageRun.stage], StageRun.duration_ms.is_not(None), STAGE_BUCKETS_S)
        emit("radar_records", "Normalized records by status", "gauge",
             [({"status": st}, n) for st, n in s.execute(select(Record.status, func.count()).group_by(Record.status))])
        emit("radar_raw_records", "Raw records by source and transport", "gauge",
             [({"source": src, "via": via}, n) for src, via, n in
              s.execute(select(RawRecord.source_id, RawRecord.received_via, func.count()).group_by(RawRecord.source_id, RawRecord.received_via))])
        emit("radar_cards", "Innovation cards by operator decision", "gauge",
             [({"decision": d}, n) for d, n in s.execute(select(Card.decision, func.count()).group_by(Card.decision))])
        avg = s.scalar(select(func.avg(Card.score)))
        emit("radar_card_score_avg", "Average card score (0-100)", "gauge", [({}, round(avg or 0, 2))])
        likes = s.scalar(select(func.coalesce(func.sum(Card.likes), 0)))
        emit("radar_likes_total", "Likes on briefs", "counter", [({}, likes or 0)])
        providers: dict[tuple, int] = {}
        fallbacks = 0
        for prov in s.scalars(select(Card.provenance)):
            prov = prov or {}
            key = (prov.get("provider") or "none", prov.get("model") or "none")
            providers[key] = providers.get(key, 0) + 1
            fallbacks += len(prov.get("fallbacks") or [])
        emit("radar_llm_extractions_total", "Extractions by LLM provider/model", "counter",
             [({"provider": p, "model": m}, n) for (p, m), n in providers.items()])
        emit("radar_llm_fallbacks_total", "Provider fallbacks during extraction", "counter", [({}, fallbacks)])
        # every LLM call (extract, agent steps, reviewer), written by the workers' router
        calls = s.execute(select(LlmCall.provider, LlmCall.model, LlmCall.purpose, LlmCall.ok, func.count(),
                                 func.coalesce(func.sum(LlmCall.tokens_in), 0), func.coalesce(func.sum(LlmCall.tokens_out), 0))
                          .group_by(LlmCall.provider, LlmCall.model, LlmCall.purpose, LlmCall.ok)).all()
        emit("radar_llm_requests_total", "LLM calls by provider, purpose and outcome", "counter",
             [({"provider": p, "model": m or "", "purpose": pu, "outcome": "ok" if ok else "error"}, n) for p, m, pu, ok, n, _, _ in calls])
        tok: dict[tuple, list] = {}
        for p, m, pu, ok, n, ti, to in calls:
            t = tok.setdefault((p, m or ""), [0, 0])
            t[0] += ti or 0
            t[1] += to or 0
        emit("radar_llm_tokens_total", "Tokens reported by the LLM API", "counter",
             [({"provider": p, "model": m, "direction": d}, v) for (p, m), (ti, to) in tok.items() for d, v in (("in", ti), ("out", to))])
        prices = _prices()
        emit("radar_llm_cost_usd_total", "Estimated LLM cost (RADAR_LLM_PRICES, USD per 1M tokens; local model = 0)", "counter",
             [({"provider": p, "model": m}, round((ti * prices.get(p, [0, 0])[0] + to * prices.get(p, [0, 0])[1]) / 1e6, 6))
              for (p, m), (ti, to) in tok.items()])
        _cost_rule_metrics(s, emit)
        _histogram(s, out, "radar_llm_latency_seconds", "Latency of successful LLM calls", LlmCall.latency_ms,
                   [LlmCall.provider, LlmCall.purpose], LlmCall.ok.is_(True), LLM_BUCKETS_S)
        now = time.time()
        src_rows, age_rows, fail_rows = [], [], []
        for st in s.scalars(select(SourceState)):
            c = st.counters or {}
            src_rows.append(({"source": st.source_id}, c.get("accepted", 0)))
            if st.last_run_at:
                age_rows.append(({"source": st.source_id}, round(now - st.last_run_at.timestamp(), 1)))
            fail_rows.append(({"source": st.source_id}, 1 if st.last_status == "failed" else 0))
        emit("radar_source_last_accepted", "Records accepted in the last harvest", "gauge", src_rows)
        emit("radar_source_last_run_age_seconds", "Seconds since the last harvest of a source", "gauge", age_rows)
        emit("radar_source_failed", "1 if the last harvest failed", "gauge", fail_rows)
    try:  # schedule per source, so the alert "no harvest for 2x the schedule" needs no hard-coded interval
        from radar.sources.registry import active_sources

        sched = [({"source": sid}, float(sp.schedule_s)) for sid, sp in active_sources().items() if sp.mode == "pull" and sp.schedule_s]
    except Exception:
        sched = []
    emit("radar_source_schedule_seconds", "Configured harvest interval (schedule_s)", "gauge", sched)

    q = _rabbit_queues()
    emit("radar_queue_messages", "Messages ready in RabbitMQ queues", "gauge",
         [({"queue": x["name"]}, x.get("messages_ready", 0)) for x in q])
    emit("radar_queue_unacked", "Messages delivered but not yet acked", "gauge",
         [({"queue": x["name"]}, x.get("messages_unacknowledged", 0)) for x in q])
    emit("radar_queue_consumers", "Consumers per queue", "gauge", [({"queue": x["name"]}, x.get("consumers", 0)) for x in q])
    emit("radar_dlq_messages", "Messages in dead-letter queues", "gauge",
         [({"queue": x["name"]}, x.get("messages", 0)) for x in q if x["name"].endswith(".dlq")])
    emit("radar_up_seconds", "Process uptime", "gauge", [({}, round(time.time() - _STARTED, 1))])
    return "\n".join(out) + "\n"


class JsonFormatter(logging.Formatter):
    """One JSON object per line; extra fields (raw_id, stage, source_id, task_id) are kept."""

    KEEP = ("raw_id", "stage", "source_id", "task_id", "provider", "outcome", "duration_ms")

    def format(self, record: logging.LogRecord) -> str:
        d = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"), "level": record.levelname, "logger": record.name, "msg": record.getMessage()}
        for k in self.KEEP:
            if hasattr(record, k):
                d[k] = getattr(record, k)
        if record.exc_info:
            d["exc"] = self.formatException(record.exc_info)
        return json.dumps(d, ensure_ascii=False)


def setup_logging() -> None:
    if os.environ.get("RADAR_LOG_FORMAT", "json") != "json":
        return
    h = logging.StreamHandler()
    h.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [h]
    root.setLevel(os.environ.get("RADAR_LOG_LEVEL", "INFO"))
