"""In-process cache for the read-heavy API endpoints (issue #31: /api/match, /api/ideas, /api/clusters under load).

An entry is keyed by the endpoint name and its normalized query parameters, and is valid only while the *data version*
is unchanged and it is younger than TTL. The data version is one cheap aggregate query over cards and records
(count, max id, sum of likes and scores, decisions, last record update), so:
- a new card from the pipeline (harvest) changes the version and invalidates everything at once;
- a like changes the sum of likes, so a list never shows an old like count;
- an operator decision changes the decision counters.
Each process (uvicorn worker, Celery worker) has its own cache; there is nothing to invalidate across processes because
every read checks the version in the shared database. Tests call reset_api_cache() between databases.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from sqlalchemy import case, func, select

from radar.db import session
from radar.models import Card, Record

TTL = 300.0
MAX_ENTRIES = 1024
_STORE: dict[tuple, tuple[tuple, float, Any]] = {}
_LOCK = threading.Lock()
STATS = {"hits": 0, "misses": 0}


def data_version(s) -> tuple:
    c = s.execute(select(func.count(Card.id), func.max(Card.id), func.sum(Card.likes), func.sum(Card.score),
                         func.count(Card.decided_at), func.sum(case((Card.decision == "approved", 1), else_=0)),
                         func.sum(case((Card.decision == "rejected", 1), else_=0)))).one()
    r = s.execute(select(func.count(Record.id), func.max(Record.updated_at))).one()
    return tuple(c) + tuple(r)


def cached(name: str, params: tuple, compute: Callable[[], Any]) -> Any:
    """Value of compute() for (name, params), recomputed when the data version changes or after TTL.
    The returned object is shared between requests: callers must not mutate it."""
    with session() as s:
        version = data_version(s)
    key, now = (name, params), time.monotonic()
    hit = _STORE.get(key)
    if hit is not None and hit[0] == version and now - hit[1] < TTL:
        STATS["hits"] += 1
        return hit[2]
    STATS["misses"] += 1
    value = compute()
    with _LOCK:
        if len(_STORE) >= MAX_ENTRIES:
            _STORE.clear()  # bounded memory; random profiles must not grow it forever
        _STORE[key] = (version, now, value)
    return value


def reset_api_cache() -> None:
    with _LOCK:
        _STORE.clear()
    STATS.update(hits=0, misses=0)
