"""Source contract.

Every data source, whatever the transport, ends as a list of `Envelope`s handed to `radar.ingest.ingest()`.

* **Pull** connectors (REST, GraphQL, OAI-PMH, SPARQL, file snapshot) are run by the `harvest` task on a schedule.
  They yield `Page`s; the cursor of each page is checkpointed, so a crashed run resumes where it stopped.
* **Push** transports (HTTP webhook, AMQP, Google Pub/Sub, Kafka) receive bytes and use `PushAdapter.parse()`.

A source is described declaratively in `sources.yaml` (`SourceSpec`); adding a new REST/GraphQL/webhook source
needs config only. A new protocol needs one class registered in `radar.sources.registry`.
"""

from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Literal

import jmespath
from pydantic import BaseModel, Field


class Envelope(BaseModel):
    source_id: str
    external_id: str
    payload: dict[str, Any]
    content_type: str = "application/json"
    received_via: Literal["pull", "webhook", "pubsub", "upload"] = "pull"
    deleted: bool = False


class SourceSpec(BaseModel):
    id: str
    type: str
    mode: Literal["pull", "push"] = "pull"
    enabled: bool = True
    # Snapshot sources that work without network or keys; the only ones run in demo mode.
    demo: bool = False
    description: str = ""
    # Seconds between scheduled pulls (Celery beat). None = manual only.
    schedule_s: int | None = None
    # Record kind for every item from this source (publication | project | patent | beneficiary | solution).
    kind: str = "other"
    # How to find items and their ids in a payload (JMESPath).
    record_path: str | None = None
    id_path: str = "id"
    # Normalized field -> JMESPath expression, or {"expr": ..., "transform": ...}. See radar.pipeline.normalize.
    mapping: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)

    def opt(self, key: str, default: Any = None) -> Any:
        return expand_env(self.options.get(key, default))


@dataclass
class Page:
    items: list[Envelope]
    next_cursor: str | None
    meta: dict[str, Any] = field(default_factory=dict)


_ENV = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def expand_env(value: Any) -> Any:
    """`${VAR}` / `${VAR:-default}` in config values, so secrets stay in env (Helm Secret), not in sources.yaml."""
    if isinstance(value, str):
        return _ENV.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), value)
    if isinstance(value, dict):
        return {k: expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env(v) for v in value]
    return value


def search(expr: str | None, data: Any) -> Any:
    if not expr:
        return data
    return jmespath.search(expr, data)


def items_from_payload(spec: SourceSpec, data: Any, received_via: str) -> list[Envelope]:
    """Split a payload into envelopes using `record_path` and `id_path`. Shared by pull and push sources."""
    found = search(spec.record_path, data) if spec.record_path else data
    if found is None:
        return []
    if isinstance(found, dict):
        found = [found]
    out = []
    for item in found:
        if not isinstance(item, dict):
            item = {"value": item}
        ext_id = search(spec.id_path, item)
        if ext_id in (None, ""):
            # No id: fall back to a stable hash of the content so redelivery is still idempotent.
            from radar.ingest import content_hash

            ext_id = "h:" + content_hash(item)[:32]
        out.append(Envelope(source_id=spec.id, external_id=str(ext_id), payload=item, received_via=received_via))
    return out


class PullConnector(ABC):
    def __init__(self, spec: SourceSpec):
        self.spec = spec

    @abstractmethod
    def fetch(self, cursor: str | None) -> Iterator[Page]:
        """Yield pages starting after `cursor`. The last page has next_cursor = the cursor for the next run."""


class PushAdapter:
    """Turns bytes received by any push transport into envelopes. Override `decode` for non-JSON payloads."""

    def __init__(self, spec: SourceSpec, received_via: str):
        self.spec = spec
        self.received_via = received_via

    def decode(self, body: bytes, headers: dict[str, str] | None = None) -> Any:
        return json.loads(body.decode("utf-8"))

    def parse(self, body: bytes, headers: dict[str, str] | None = None) -> list[Envelope]:
        return items_from_payload(self.spec, self.decode(body, headers), self.received_via)
