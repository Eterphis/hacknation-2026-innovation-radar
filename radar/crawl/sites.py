"""Witryny do przeglądania: config/sites.json (JSON, żeby nie dodawać zależności od YAML)."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG = "config/sites.json"
CATEGORIES = ("nauka", "projekty", "biznes", "administracja")


@dataclass
class Site:
    id: str
    name: str
    category: str
    start: list[str]
    owner: dict = field(default_factory=dict)       # {"name", "type", "voivodeship"}
    use_sitemap: bool = True
    include: list[str] = field(default_factory=list)  # regexes on path+query; empty = everything
    exclude: list[str] = field(default_factory=list)
    follow: list[str] = field(default_factory=list)   # pages to follow links from but not to keep (lists)
    max_pages: int = 150
    max_depth: int = 3
    interval_hours: float = 24.0
    revisit_days: float = 14.0
    delay: float = 2.0
    keep_all: bool = False       # keep every page with enough text (curated project lists)
    min_score: float = 2.0
    require_date: bool = False   # keep only pages with a publication date (drops hub/menu pages on portals)
    enabled: bool = True
    note: str = ""

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_]{0,40}", self.id):
            raise ValueError(f"niepoprawne id witryny: {self.id!r} (małe litery, cyfry, _)")
        if self.category not in CATEGORIES:
            raise ValueError(f"{self.id}: kategoria {self.category!r} spoza {CATEGORIES}")
        if not self.start:
            raise ValueError(f"{self.id}: brak adresów startowych")
        self._inc = [re.compile(p) for p in self.include]
        self._exc = [re.compile(p) for p in self.exclude]
        self._fol = [re.compile(p) for p in self.follow]

    @property
    def source(self) -> str:
        return f"web_{self.id}"

    def matches(self, path_query: str) -> bool:
        if any(r.search(path_query) for r in self._exc):
            return False
        return not self._inc or any(r.search(path_query) for r in self._inc) or self.is_follow(path_query)

    def is_follow(self, path_query: str) -> bool:
        return any(r.search(path_query) for r in self._fol)

    def to_json(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


def config_path() -> Path:
    return Path(os.environ.get("RADAR_SITES") or DEFAULT_CONFIG)


def load_sites(path: str | Path | None = None, only_enabled: bool = True) -> list[Site]:
    path = Path(path) if path else config_path()
    if not path.exists():
        return []
    data = json.loads(path.read_text("utf-8"))
    sites = [Site(**{k: v for k, v in s.items() if not k.startswith("_")}) for s in data.get("sites", [])]
    ids = [s.id for s in sites]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise ValueError(f"powtórzone id witryn: {', '.join(sorted(dup))}")
    return [s for s in sites if s.enabled or not only_enabled]
