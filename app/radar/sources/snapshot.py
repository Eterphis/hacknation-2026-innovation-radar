"""File snapshot connector: JSON, JSONL or CSV on disk (demo mode, manual exports such as UPRP or Kohesio CSV).

options: path (relative paths resolve against the sources.yaml directory), format (auto | json | jsonl | csv),
         csv_delimiter (",")
Same code path as live connectors: the snapshot is just another source.
"""

import csv
import json
from collections.abc import Iterator
from pathlib import Path

from radar.config import get_settings
from radar.sources.base import Page, PullConnector, items_from_payload


def resolve_path(p: str) -> Path:
    """Relative paths: next to sources.yaml first, then the working directory (Helm mounts sources.yaml from a
    ConfigMap at /config while the samples stay in the image under /app)."""
    path = Path(p)
    if path.is_absolute():
        return path
    beside = Path(get_settings().sources_file).resolve().parent / path
    return beside if beside.exists() else Path.cwd() / path


class SnapshotConnector(PullConnector):
    def fetch(self, cursor: str | None) -> Iterator[Page]:
        path = resolve_path(self.spec.opt("path"))
        if not path.exists() and self.spec.opt("optional", False):
            # e.g. a harvester output (radar.refresh) not produced yet: nothing to ingest, not an error
            yield Page(items=[], next_cursor=None, meta={"missing": str(path)})
            return
        fmt = self.spec.opt("format", "auto")
        if fmt == "auto":
            fmt = path.suffix.lstrip(".").lower()
        text = path.read_text(encoding="utf-8-sig")
        if fmt == "jsonl":
            data = [json.loads(line) for line in text.splitlines() if line.strip()]
        elif fmt == "csv":
            data = list(csv.DictReader(text.splitlines(), delimiter=self.spec.opt("csv_delimiter", ",")))
        else:
            data = json.loads(text)
        yield Page(items=items_from_payload(self.spec, data, "pull"), next_cursor=None)
