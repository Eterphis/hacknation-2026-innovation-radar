"""Regression: a freshly trained head is used right away, even when time.monotonic() is small (CI VM just booted)."""

import time

from radar.basal import classifier as C


def test_trained_head_used_on_fresh_machine(monkeypatch):
    monkeypatch.setattr(time, "monotonic", lambda: 5.0)  # 5 s since boot, less than the 60 s cache TTL
    b = C.classify(title="Program dla seniorów w gminie", abstract="Gmina uruchomiła program wsparcia seniorów prowadzony "
                   "przez ośrodek pomocy społecznej, działa od roku. " * 3, affiliations=["Gmina Sanok"], min_chars=80)
    assert b["learned_accept"] is None  # no head yet; this also fills the cache with "no head"
    rows = [(b, i % 2) for i in range(8)]
    assert C.train_head(rows)["trained"]
    again = C.classify(title="Program dla seniorów w gminie", abstract="Gmina uruchomiła program wsparcia seniorów "
                       "prowadzony przez ośrodek pomocy społecznej, działa od roku. " * 3, affiliations=["Gmina Sanok"], min_chars=80)
    assert again["learned_accept"] is not None
