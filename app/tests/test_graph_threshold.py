"""Corpus-adaptive "similar" threshold of the idea graph (PR #11 review, risk 2)."""

import numpy as np
from sqlalchemy import func, select

from radar.basal import graph
from radar.basal.embed import CALIBRATION
from radar.db import session
from radar.models import Edge
from radar.pipeline.tasks import harvest

CAL = CALIBRATION["hashing"]


def _unit(rows: np.ndarray) -> np.ndarray:
    return (rows / np.linalg.norm(rows, axis=1, keepdims=True)).astype(np.float32)


def test_threshold_is_the_quantile_clamped_to_the_calibrated_range():
    rng = np.random.default_rng(0)
    spread = _unit(rng.normal(size=(60, 64)))                       # unrelated texts: pairs ~0 -> floor
    assert graph._quantile_threshold(spread, CAL) == CAL["similar_floor"]
    shared = _unit(rng.normal(size=(60, 64)) * 0.3 + rng.normal(size=64))  # shared vocabulary: pairs ~0.9 -> ceiling
    assert graph._quantile_threshold(shared, CAL) == CAL["similar_min"]
    mid = _unit(rng.normal(size=(60, 64)) + rng.normal(size=64) * 0.55)    # in between: the quantile itself
    t = graph._quantile_threshold(mid, CAL)
    assert CAL["similar_floor"] < t < CAL["similar_min"]


def test_small_corpus_keeps_the_calibrated_threshold():
    rng = np.random.default_rng(1)
    assert graph._quantile_threshold(_unit(rng.normal(size=(graph.MIN_CORPUS - 1, 16))), CAL) == CAL["similar_min"]


def test_demo_keeps_its_similarity_edges():
    """Short synthetic demo records (median pair ~0.07): the fixed 0.35 of PR #11 linked none of these 19 records
    (`radar demo` with every demo source: 3 edges instead of main's 21); the adaptive threshold falls to the floor."""
    harvest.apply(("demo-zgloszenia",)).get()
    with session() as s:
        n = s.scalar(select(func.count()).select_from(Edge))
        t = graph.similar_min(s)
    assert t == CAL["similar_floor"]
    assert n >= 8, n
