import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, Integer, String, Text, false, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, Timestamps, UUIDPk, pg_enum


class RequestStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    FULFILLED = "fulfilled"
    REJECTED = "rejected"


class ContentRequest(UUIDPk, Timestamps, Base):
    """A trainer's request for additional content, routed to the developer."""

    __tablename__ = "content_requests"

    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    topic_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"))
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300))
    details: Mapped[str] = mapped_column(Text)
    # Request Router agent output: category, priority, suggested sources
    triage: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[RequestStatus] = mapped_column(
        pg_enum(RequestStatus, "request_status"), server_default=RequestStatus.OPEN.value
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AgentRun(UUIDPk, CreatedAt, Base):
    __tablename__ = "agent_runs"

    agent: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[AgentRunStatus] = mapped_column(
        pg_enum(AgentRunStatus, "agent_run_status"), server_default=AgentRunStatus.QUEUED.value
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    class_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("classes.id", ondelete="SET NULL"))
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL")
    )
    input: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    output: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ModelVersion(UUIDPk, CreatedAt, Base):
    """A fine-tuned model build. Exactly one may be active at a time."""

    __tablename__ = "model_versions"
    __table_args__ = (
        Index("uq_model_versions_active", "is_active", unique=True, postgresql_where=text("is_active")),
    )

    name: Mapped[str] = mapped_column(String(128), unique=True)
    base_model: Mapped[str] = mapped_column(String(128))
    artifact_uri: Mapped[str | None] = mapped_column(String(1024))
    quantization: Mapped[str | None] = mapped_column(String(32))
    eval_scores: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    is_active: Mapped[bool] = mapped_column(server_default=false())
    notes: Mapped[str | None] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
