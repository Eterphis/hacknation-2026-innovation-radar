"""Storage layers from pipeline-design.md: raw -> normalized (Record) -> enriched (Card).

Every stage writes a StageRun row keyed by (raw_id, stage, content_hash). That key is the idempotency guard
(D-005 "no record lost or processed twice"): a redelivered message for the same content is a no-op, and
stage counters can be reconciled from this table alone.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from radar.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RawRecord(Base):
    __tablename__ = "raw_records"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_raw_source_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(100), index=True)
    external_id: Mapped[str] = mapped_column(String(500))
    content_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    # new | updated | unchanged | deleted
    status: Mapped[str] = mapped_column(String(20), default="new")
    content_type: Mapped[str] = mapped_column(String(50), default="application/json")
    # pull | webhook | pubsub | upload
    received_via: Mapped[str] = mapped_column(String(20), default="pull")
    payload: Mapped[dict] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    record: Mapped["Record | None"] = relationship(back_populates="raw", uselist=False)


class Record(Base):
    __tablename__ = "records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    raw_id: Mapped[int] = mapped_column(ForeignKey("raw_records.id"), unique=True)
    source_id: Mapped[str] = mapped_column(String(100), index=True)
    # publication | project | patent | beneficiary | solution | other
    kind: Mapped[str] = mapped_column(String(30), default="other")
    title: Mapped[str | None] = mapped_column(Text)
    abstract: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(10))
    year: Mapped[int | None] = mapped_column(Integer)
    doi: Mapped[str | None] = mapped_column(String(300), index=True)
    url: Mapped[str | None] = mapped_column(Text)
    authors: Mapped[list] = mapped_column(JSON, default=list)
    affiliations: Mapped[list] = mapped_column(JSON, default=list)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    licence: Mapped[str | None] = mapped_column(String(200))
    region: Mapped[str | None] = mapped_column(String(100))
    amounts: Mapped[dict] = mapped_column(JSON, default=dict)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    # normalized | needs_review | duplicate | not_innovation | extracted | ready | deleted
    status: Mapped[str] = mapped_column(String(20), default="normalized", index=True)
    review_reasons: Mapped[list] = mapped_column(JSON, default=list)
    cluster_id: Mapped[int | None] = mapped_column(Integer, index=True)
    # Basal result (full) + denormalized labels for filtering and facets
    basal: Mapped[dict] = mapped_column(JSON, default=dict)
    sector: Mapped[str | None] = mapped_column(String(40), index=True)
    tech_area: Mapped[str | None] = mapped_column(String(40), index=True)
    innovation_type: Mapped[str | None] = mapped_column(String(30), index=True)
    institution_type: Mapped[str | None] = mapped_column(String(30), index=True)
    voivodeship: Mapped[str | None] = mapped_column(String(40), index=True)
    cost_level: Mapped[str | None] = mapped_column(String(20), index=True)
    priority: Mapped[float | None] = mapped_column(Float)
    embedding: Mapped[list | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    raw: Mapped[RawRecord] = relationship(back_populates="record")
    card: Mapped["Card | None"] = relationship(back_populates="record", uselist=False)


class StageRun(Base):
    __tablename__ = "stage_runs"
    __table_args__ = (UniqueConstraint("raw_id", "stage", "content_hash", name="uq_stage_idempotency"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    raw_id: Mapped[int] = mapped_column(ForeignKey("raw_records.id"), index=True)
    stage: Mapped[str] = mapped_column(String(30), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    # ok | needs_review | skipped | failed
    outcome: Mapped[str] = mapped_column(String(20))
    detail: Mapped[str | None] = mapped_column(Text)
    # wall time of the stage body (ms), for the stage latency metrics
    duration_ms: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LlmCall(Base):
    """One call to an LLM provider (extract, agent step, reviewer). Workers write it, /metrics on the API reads it,
    so latency and errors per provider are visible without a multiprocess metrics registry."""

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(30), index=True)
    model: Mapped[str | None] = mapped_column(String(120))
    purpose: Mapped[str] = mapped_column(String(30), index=True)  # extract | agent | review | other
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    latency_ms: Mapped[float] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(String(300))
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Card(Base):
    """Karta innowacji: what the operator approves or rejects."""

    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("records.id"), unique=True)
    solution_name: Mapped[str | None] = mapped_column(Text)
    problem_solved: Mapped[str | None] = mapped_column(Text)
    what_is_new: Mapped[str | None] = mapped_column(Text)
    target_users: Mapped[list] = mapped_column(JSON, default=list)
    innovation_type: Mapped[str | None] = mapped_column(String(30))
    summary_pl: Mapped[str | None] = mapped_column(Text)
    # field -> {"quote": str, "confidence": float}; every quote is checked against the source text.
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    maturity: Mapped[str | None] = mapped_column(String(20))
    missing: Mapped[list] = mapped_column(JSON, default=list)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    # ordered reasoning steps shown to the clerk (ustalenia -> kryteria -> ocena -> rozstrzygnięcie)
    reasoning: Mapped[list] = mapped_column(JSON, default=list)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    # agent output: paths (who does what), risks + mitigations, recipients, criteria scores, metrics, recheck
    assessment: Mapped[dict] = mapped_column(JSON, default=dict)
    brief: Mapped[dict] = mapped_column(JSON, default=dict)
    score: Mapped[float | None] = mapped_column(Float, index=True)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    # pending | approved | rejected
    decision: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    decision_note: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    record: Mapped[Record] = relationship(back_populates="card")


class Edge(Base):
    """Graph edge between two records (similar idea). Hub edges (sector, region, org) are derived at query time."""

    __tablename__ = "edges"
    __table_args__ = (UniqueConstraint("src_id", "dst_id", "kind", name="uq_edge"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    src_id: Mapped[int] = mapped_column(ForeignKey("records.id"), index=True)
    dst_id: Mapped[int] = mapped_column(ForeignKey("records.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # similar | possible_duplicate
    weight: Mapped[float] = mapped_column(Float)


class Like(Base):
    __tablename__ = "likes"
    __table_args__ = (UniqueConstraint("card_id", "voter", name="uq_like"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), index=True)
    voter: Mapped[str] = mapped_column(String(64))  # anonymous browser id (hash); accounts later (D-010)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Setting(Base):
    """Small shared key/value store (e.g. Basal's learned decision head), visible to every pod."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SourceState(Base):
    __tablename__ = "source_state"

    source_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    cursor: Mapped[str | None] = mapped_column(Text)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(20))
    last_error: Mapped[str | None] = mapped_column(Text)
    counters: Mapped[dict] = mapped_column(JSON, default=dict)
