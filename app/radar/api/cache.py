"""In-process cache for the read-heavy API endpoints (issue #31: /api/match, /api/ideas, /api/clusters under load).

An entry is keyed by the endpoint name and its normalized query parameters, and is valid only while the *data version*
is unchanged and it is younger than TTL. The data version is one cheap aggregate query over cards and records
(count, max id, sum of likes and scores, decisions, last record update), so:
- a new card from the pipeline (harvest) changes the version and invalidates everything at once;
- a like does not invalidate anything: like counts inside cached answers are overlaid from a small id->likes map
  refreshed with the version (a like used to recompute every list for everyone);
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
_FLIGHTS: dict[tuple, threading.Lock] = {}
STATS = {"hits": 0, "misses": 0}


def data_version(s) -> tuple:
    """What invalidates cached answers: new or rescored cards, decisions, record changes. Not likes: a like would
    otherwise recompute every list for everyone (measured: 53 -> 7 rps on real data); like counts are refreshed
    in place instead (see _overlay_likes)."""
    return _version_and_likes(s)[0]


def _version_and_likes(s) -> tuple[tuple, int | None]:
    c = s.execute(select(func.count(Card.id), func.max(Card.id), func.sum(Card.score),
                         func.count(Card.decided_at), func.sum(case((Card.decision == "approved", 1), else_=0)),
                         func.sum(case((Card.decision == "rejected", 1), else_=0)), func.sum(Card.likes))).one()
    r = s.execute(select(func.count(Record.id), func.max(Record.updated_at))).one()
    return tuple(c)[:-1] + tuple(r), c[-1]


def cached(name: str, params: tuple, compute: Callable[[], Any]) -> Any:
    """Value of compute() for (name, params), recomputed when the data version changes or after TTL; like counts
    inside it are always current. The returned object is shared between requests: callers must not mutate it."""
    version = _current_version()
    key = (name, params)
    hit = _fresh(key, version)
    if hit is None:
        # single flight: under a burst, one thread computes a missing entry and the others wait for it instead of
        # computing the same thing in parallel (which on real data saturated the CPU and the memory limit)
        with _LOCK:
            lock = _FLIGHTS.setdefault(key, threading.Lock())
        with lock:
            hit = _fresh(key, version)
            if hit is None:
                STATS["misses"] += 1
                value = compute()
                hit = [version, time.monotonic(), value, _like_refs(value), None]
                with _LOCK:
                    if len(_STORE) >= MAX_ENTRIES:
                        _STORE.clear()  # bounded memory; random profiles must not grow it forever
                    _STORE[key] = hit
                    _FLIGHTS.pop(key, None)
                _overlay_likes(hit)
                return value
    STATS["hits"] += 1
    _overlay_likes(hit)
    return hit[2]


VERSION_TTL = 2.0  # the version query scans cards and records: under load ask it at most every 2 s per process
_VERSION: list = [None, -1e9, None]  # version, when read, sum of likes
_LIKES: dict[int, int] = {}


def _current_version() -> tuple:
    now = time.monotonic()
    if _VERSION[0] is None or now - _VERSION[1] >= VERSION_TTL:
        with session() as s:
            version, total = _version_and_likes(s)
            if total != _VERSION[2]:  # someone liked: one small read of the like counts, nothing recomputed
                _LIKES.clear()
                _LIKES.update(s.execute(select(Card.id, Card.likes)).all())
        _VERSION[:] = [version, now, total]
    return _VERSION[0]


def _like_refs(value: Any) -> list[dict]:
    """Every dict in a cached answer that shows a card's like count (lists, nested sections, the match corpus)."""
    out, stack = [], [value]
    while stack:
        v = stack.pop()
        if isinstance(v, dict):
            if "card_id" in v and "likes" in v:
                out.append(v)
            stack.extend(v.values())
        elif isinstance(v, (list, tuple)):
            stack.extend(v)
    return out


def _overlay_likes(hit: list) -> None:
    if hit[4] == _VERSION[2]:
        return
    for d in hit[3]:
        d["likes"] = _LIKES.get(d["card_id"], d["likes"])
    hit[4] = _VERSION[2]


def _fresh(key: tuple, version: tuple):
    hit = _STORE.get(key)
    return hit if hit is not None and hit[0] == version and time.monotonic() - hit[1] < TTL else None


def reset_api_cache() -> None:
    with _LOCK:
        _STORE.clear()
        _FLIGHTS.clear()
    _VERSION[:] = [None, -1e9, None]
    _LIKES.clear()
    STATS.update(hits=0, misses=0)
