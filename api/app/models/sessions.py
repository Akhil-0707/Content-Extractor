import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, Timestamps, UUIDPk, pg_enum


class SessionStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class TrainingSession(UUIDPk, Timestamps, Base):
    __tablename__ = "training_sessions"

    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer)
    status: Mapped[SessionStatus] = mapped_column(
        pg_enum(SessionStatus, "session_status"), server_default=SessionStatus.DRAFT.value
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ItemType(StrEnum):
    CONTENT = "content"
    QUIZ = "quiz"
    POLL = "poll"


class ReviewStatus(StrEnum):
    GENERATED = "generated"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"


class SessionItem(UUIDPk, Timestamps, Base):
    """One step of a session: a content step, a pop quiz, or a poll."""

    __tablename__ = "session_items"
    __table_args__ = (
        UniqueConstraint("session_id", "position"),
        CheckConstraint(
            "item_type = 'content' OR (question IS NOT NULL AND options IS NOT NULL)",
            name="question_items_have_options",
        ),
        CheckConstraint("item_type <> 'quiz' OR correct_option IS NOT NULL", name="quiz_has_answer"),
        CheckConstraint("xp_reward >= 0", name="xp_reward_non_negative"),
        CheckConstraint("time_limit_seconds IS NULL OR time_limit_seconds > 0", name="time_limit_positive"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("training_sessions.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    item_type: Mapped[ItemType] = mapped_column(pg_enum(ItemType, "item_type"))
    topic_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"))
    body_markdown: Mapped[str | None] = mapped_column(Text)
    question: Mapped[str | None] = mapped_column(Text)
    options: Mapped[list | None] = mapped_column(JSONB)
    # Polls may have no correct answer (opinion polls award no XP)
    correct_option: Mapped[int | None] = mapped_column(Integer)
    xp_reward: Mapped[int] = mapped_column(Integer, server_default="0")
    time_limit_seconds: Mapped[int | None] = mapped_column(Integer)
    source_refs: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    review_status: Mapped[ReviewStatus] = mapped_column(
        pg_enum(ReviewStatus, "review_status"), server_default=ReviewStatus.GENERATED.value
    )
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL")
    )


class LiveRun(UUIDPk, Base):
    """A trainer-led, synchronized run of a session."""

    __tablename__ = "live_runs"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="CASCADE"), index=True
    )
    started_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    current_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("session_items.id", ondelete="SET NULL"))
    item_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    item_closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SessionMode(StrEnum):
    LIVE = "live"
    SELF_PACED = "self_paced"


class ProgressStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class SessionProgress(UUIDPk, Base):
    """A trainee's attempt at a session. 'Start from the beginning' creates a new attempt."""

    __tablename__ = "session_progress"
    __table_args__ = (UniqueConstraint("user_id", "session_id", "attempt"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="CASCADE"), index=True
    )
    attempt: Mapped[int] = mapped_column(Integer, server_default="1")
    mode: Mapped[SessionMode] = mapped_column(pg_enum(SessionMode, "session_mode"))
    current_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("session_items.id", ondelete="SET NULL"))
    completed_items: Mapped[int] = mapped_column(Integer, server_default="0")
    status: Mapped[ProgressStatus] = mapped_column(
        pg_enum(ProgressStatus, "progress_status"), server_default=ProgressStatus.IN_PROGRESS.value
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Response(UUIDPk, Base):
    __tablename__ = "responses"
    __table_args__ = (UniqueConstraint("progress_id", "session_item_id"),)

    session_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("session_items.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    progress_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("session_progress.id", ondelete="CASCADE"))
    live_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("live_runs.id", ondelete="SET NULL"))
    # NULL chosen_option = time ran out; NULL is_correct = poll without a correct answer
    chosen_option: Mapped[int | None] = mapped_column(Integer)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class XpReason(StrEnum):
    INITIAL = "initial"
    QUIZ_CORRECT = "quiz_correct"
    POLL_CORRECT = "poll_correct"
    MANUAL_ADJUSTMENT = "manual_adjustment"


class XpLedger(UUIDPk, CreatedAt, Base):
    """Append-only XP history. A trainee's XP in a class is SUM(amount)."""

    __tablename__ = "xp_ledger"
    __table_args__ = (
        Index("ix_xp_ledger_user_class", "user_id", "class_id"),
        # XP for a given quiz/poll item is awarded at most once per trainee, even across restarts
        Index(
            "uq_xp_ledger_user_item",
            "user_id",
            "session_item_id",
            unique=True,
            postgresql_where=text("session_item_id IS NOT NULL"),
        ),
        Index(
            "uq_xp_ledger_user_class_initial",
            "user_id",
            "class_id",
            unique=True,
            postgresql_where=text("reason = 'initial'"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"))
    amount: Mapped[int] = mapped_column(Integer)
    reason: Mapped[XpReason] = mapped_column(pg_enum(XpReason, "xp_reason"))
    session_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("session_items.id", ondelete="SET NULL"))
    response_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("responses.id", ondelete="SET NULL"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(String(300))


class SessionSummary(UUIDPk, CreatedAt, Base):
    __tablename__ = "session_summaries"

    progress_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("session_progress.id", ondelete="CASCADE"), index=True
    )
    summary_markdown: Mapped[str] = mapped_column(Text)
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL")
    )
