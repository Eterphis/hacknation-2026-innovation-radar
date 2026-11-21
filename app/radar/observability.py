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
from sqlalchemy import func, select

from radar.config import get_settings
from radar.db import session
from radar.models import Card, RawRecord, Record, SourceState, StageRun

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

    KEEP = ("raw_id", "stage", "source_id", "task_id", "provider")

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
