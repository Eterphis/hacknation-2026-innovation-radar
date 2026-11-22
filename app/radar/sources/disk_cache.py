"""Tiny on-disk JSON cache for registry clients (EPO OPS, KRS, calls): one file per key, with a TTL.

Registries change slowly and have strict quotas, so a fetched answer is kept on disk and reused across runs and
workers. The cache directory comes from RADAR_REGISTRY_CACHE; without it, data/cache/registries next to the app when
that is writable, else <tmp>/radar-registries (the container runs as a non-root user and only /tmp is writable).
Each entry stores when it was fetched, so callers can report the date with every value.

The cache never makes a source fail: an unreadable entry is a miss, and an entry that cannot be written (read-only
disk, full disk, permissions) is returned without being stored.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "registries"
FALLBACK_DIR = Path(tempfile.gettempdir()) / "radar-registries"


def _writable(path: Path) -> bool:
    """True when `path` exists and is writable, or its nearest existing parent is."""
    for p in (path, *path.parents):
        if p.exists():
            return os.access(p, os.W_OK)
    return False


def default_root() -> Path:
    env = os.environ.get("RADAR_REGISTRY_CACHE")
    if env:
        return Path(env)
    return DEFAULT_DIR if _writable(DEFAULT_DIR) else FALLBACK_DIR


class DiskCache:
    def __init__(self, namespace: str, ttl_s: float = 7 * 86400, root: str | Path | None = None):
        self.dir = Path(root or default_root()) / namespace
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
        if not isinstance(entry, dict) or time.time() - entry.get("ts", 0) > self.ttl_s:
            return None
        return entry

    def put(self, key: str, value: Any) -> dict:
        """Store and return the entry. Raises OSError when the disk refuses; `fetch` swallows that."""
        entry = {"key": key, "ts": time.time(),
                 "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "value": value}
        self.dir.mkdir(parents=True, exist_ok=True)
        # a unique temp file per writer: two workers storing the same key never write into one file
        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(entry, f, ensure_ascii=False)
            os.replace(tmp, self._path(key))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return entry

    def fetch(self, key: str, loader: Callable[[], Any]) -> dict:
        """Cached entry, or call `loader` and store its result (returned unstored when the disk refuses)."""
        hit = self.get(key)
        if hit is not None:
            return hit
        value = loader()
        try:
            return self.put(key, value)
        except OSError:
            return {"key": key, "ts": time.time(),
                    "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "value": value}
