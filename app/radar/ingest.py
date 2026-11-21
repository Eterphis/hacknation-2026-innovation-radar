"""Single entry point for every source (pull, webhook, pub/sub, manual upload).

Dedup layer 1 (pipeline-design §16): same (source_id, external_id) with the same content_hash -> `unchanged`,
not processed again. A different hash -> new version, re-processed from `normalize`.
The raw row is committed before the pipeline message is sent, so a lost message can be re-sent from the DB
(`radar reconcile`), and the message itself carries only ids.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select

from radar.db import session
from radar.models import RawRecord, utcnow
from radar.sources.base import Envelope


def content_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def store(env: Envelope) -> tuple[int, str, str]:
    """Upsert the raw record. Returns (raw_id, status, hash)."""
    h = content_hash(env.payload)
    with session() as s:
        row = s.scalar(select(RawRecord).where(RawRecord.source_id == env.source_id,
                                               RawRecord.external_id == env.external_id))
        if row is None:
            row = RawRecord(source_id=env.source_id, external_id=env.external_id, content_hash=h,
                            payload=env.payload, content_type=env.content_type, received_via=env.received_via,
                            status="deleted" if env.deleted else "new")
            s.add(row)
        elif env.deleted:
            row.status = "deleted"
            row.fetched_at = utcnow()
        elif row.content_hash == h:
            row.status = "unchanged"
            row.fetched_at = utcnow()
        else:
            row.content_hash, row.payload, row.version = h, env.payload, row.version + 1
            row.status, row.fetched_at = "updated", utcnow()
        s.flush()
        return row.id, row.status, h


def ingest_many(envelopes: list[Envelope]) -> dict[str, int]:
    from radar.pipeline.tasks import enqueue_normalize

    counts = {"accepted": 0, "new": 0, "updated": 0, "unchanged": 0, "deleted": 0}
    for env in envelopes:
        raw_id, status, h = store(env)
        counts["accepted"] += 1
        counts[status] += 1
        if status in ("new", "updated", "deleted"):
            enqueue_normalize(raw_id, h)
    return counts
