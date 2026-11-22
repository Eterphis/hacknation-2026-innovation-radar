"""Tiny on-disk JSON cache for registry clients (EPO OPS, KRS, calls): one file per key, with a TTL.

Registries change slowly and have strict quotas, so a fetched answer is kept on disk and reused across runs and
workers. The cache directory comes from RADAR_REGISTRY_CACHE (default: data/cache/registries next to the app).
Each entry stores when it was fetched, so callers can report the date with every value.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "registries"


class DiskCache:
    def __init__(self, namespace: str, ttl_s: float = 7 * 86400, root: str | Path | None = None):
        base = Path(root or os.environ.get("RADAR_REGISTRY_CACHE") or DEFAULT_DIR)
        self.dir = base / namespace
        self.ttl_s = ttl_s

    def _path(self, key: str) -> Path:
        return self.dir / (hashlib.sha256(key.encode("utf-8")).hexdigest()[:32] + ".json")

    def get(self, key: str) -> dict | None:
        """{"fetched_at": iso, "value": ...} or None when missing, unreadable or older than the TTL."""
        p = self._path(key)
        try:
            entry = json.loads(p.read_text("utf-8"))
        except (OSError, ValueError):
            return None
        if time.time() - entry.get("ts", 0) > self.ttl_s:
            return None
        return entry

    def put(self, key: str, value: Any) -> dict:
        entry = {"key": key, "ts": time.time(),
                 "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "value": value}
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self._path(key).with_suffix(".tmp")
        tmp.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._path(key))
        return entry

    def fetch(self, key: str, loader: Callable[[], Any]) -> dict:
        """Cached entry, or call `loader` and store its result."""
        return self.get(key) or self.put(key, loader())
