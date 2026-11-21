"""Source registry: `type` in sources.yaml -> implementation, and loading of the sources file."""

from __future__ import annotations

from pathlib import Path

import yaml

from radar.config import get_settings
from radar.sources.base import PullConnector, SourceSpec
from radar.sources.graphql import GraphQLConnector
from radar.sources.oaipmh import OaiPmhConnector
from radar.sources.rest import RestConnector
from radar.sources.snapshot import SnapshotConnector
from radar.sources.sparql import SparqlConnector

PULL_TYPES: dict[str, type[PullConnector]] = {
    "rest": RestConnector,
    "graphql": GraphQLConnector,
    "oaipmh": OaiPmhConnector,
    "sparql": SparqlConnector,
    "snapshot": SnapshotConnector,
}
# Push types are handled by radar.sources.push (consumers) and radar.api (webhook).
PUSH_TYPES = {"webhook", "amqp", "gcp_pubsub", "kafka"}


def register(type_name: str, cls: type[PullConnector]) -> None:
    """Extension point for a new pull protocol (e.g. SOAP, FTP)."""
    PULL_TYPES[type_name] = cls


def load_sources(path: str | None = None) -> dict[str, SourceSpec]:
    p = Path(path or get_settings().sources_file)
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    specs = {}
    for raw in data.get("sources", []):
        spec = SourceSpec(**raw)
        if spec.type in PUSH_TYPES:
            spec.mode = "push"
        elif spec.type not in PULL_TYPES:
            raise ValueError(f"source {spec.id}: unknown type {spec.type!r}")
        if spec.id in specs:
            raise ValueError(f"duplicate source id {spec.id!r}")
        specs[spec.id] = spec
    return specs


def active_sources() -> dict[str, SourceSpec]:
    """Demo mode: only `demo` sources. Live mode: everything enabled except synthetic snapshots."""
    demo = get_settings().demo_mode
    return {k: s for k, s in load_sources().items()
            if s.enabled and (s.demo if demo else not (s.demo and s.type == "snapshot"))}


def hidden_source_ids() -> list[str]:
    """Sources whose records the UI hides in the current mode (synthetic snapshots when running on live data)."""
    if get_settings().demo_mode:
        return []
    return [k for k, s in load_sources().items() if s.demo and s.type == "snapshot"]


def get_source(source_id: str) -> SourceSpec:
    specs = load_sources()
    if source_id not in specs:
        raise KeyError(source_id)
    return specs[source_id]


def connector(spec: SourceSpec) -> PullConnector:
    return PULL_TYPES[spec.type](spec)
