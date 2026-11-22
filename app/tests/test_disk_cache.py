"""DiskCache never makes a registry source fail (non-root container, read-only disk, parallel workers)."""

from __future__ import annotations

import os

from radar.sources import disk_cache as D
from radar.sources.disk_cache import DiskCache


def test_roundtrip_and_ttl(tmp_path):
    c = DiskCache("x", ttl_s=60, root=tmp_path)
    assert c.get("k") is None
    e = c.fetch("k", lambda: [1, 2])
    assert e["value"] == [1, 2] and e["fetched_at"]
    assert c.fetch("k", lambda: 1 / 0)["value"] == [1, 2]  # from disk, loader not called
    assert not list((tmp_path / "x").glob("*.tmp"))  # temp files never left behind
    assert DiskCache("x", ttl_s=-1, root=tmp_path).get("k") is None  # expired


def test_unwritable_disk_returns_value_unstored(tmp_path, monkeypatch):
    c = DiskCache("x", root=tmp_path)

    def refuse(*a, **kw):
        raise PermissionError("read-only")

    monkeypatch.setattr(D.tempfile, "mkstemp", refuse)
    e = c.fetch("k", lambda: {"a": 1})
    assert e["value"] == {"a": 1} and e["fetched_at"]
    assert c.get("k") is None


def test_corrupt_entry_is_a_miss(tmp_path):
    c = DiskCache("x", root=tmp_path)
    c.put("k", 1)
    c._path("k").write_text("{broken", "utf-8")
    assert c.get("k") is None
    c._path("k").write_text("[1]", "utf-8")  # valid JSON, wrong shape
    assert c.get("k") is None


def test_default_root_env_then_writable_then_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_REGISTRY_CACHE", str(tmp_path / "env"))
    assert D.default_root() == tmp_path / "env"
    monkeypatch.delenv("RADAR_REGISTRY_CACHE")
    monkeypatch.setattr(D, "DEFAULT_DIR", tmp_path / "app" / "data" / "cache")
    assert D.default_root() == tmp_path / "app" / "data" / "cache"
    monkeypatch.setattr(D.os, "access", lambda p, mode: False)  # e.g. /app owned by root, USER 10001
    assert D.default_root() == D.FALLBACK_DIR
