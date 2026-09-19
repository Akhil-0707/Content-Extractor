import uuid
from datetime import datetime
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, Timestamps, UUIDPk, pg_enum

# bge-m3 dense embedding size
EMBEDDING_DIM = 1024


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Document(UUIDPk, Timestamps, Base):
    __tablename__ = "documents"

    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    original_filename: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    storage_key: Mapped[str] = mapped_column(String(1024), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[DocumentStatus] = mapped_column(
        pg_enum(DocumentStatus, "document_status"), server_default=DocumentStatus.UPLOADED.value
    )
    error: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Topic(UUIDPk, Timestamps, Base):
    __tablename__ = "topics"

    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer)


class DocumentChunk(UUIDPk, CreatedAt, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "position"),
        Index(
            "ix_document_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    topic_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    # Where the chunk came from: {"page": 4} / {"slide": 7} / {"start_s": 812.4, "end_s": 845.0}
    source_ref: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))


class ContentStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class ContentDocument(UUIDPk, Timestamps, Base):
    __tablename__ = "content_documents"
    __table_args__ = (UniqueConstraint("topic_id", "version"),)

    topic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    body_markdown: Mapped[str] = mapped_column(Text)
    additional_info_markdown: Mapped[str | None] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    status: Mapped[ContentStatus] = mapped_column(
        pg_enum(ContentStatus, "content_status"), server_default=ContentStatus.DRAFT.value
    )
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL")
    )
    edited_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
