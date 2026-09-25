"""documents table (Section 20) — one row per uploaded file, tracking it
through the ingestion pipeline (Section 4/5).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID
from app.models.enums import DocumentStatus, DocumentType


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="SET NULL"), index=True
    )

    filename: Mapped[str] = mapped_column(String(512))
    """Sanitized name of the stored file on disk (may differ from upload name)."""
    original_filename: Mapped[str] = mapped_column(String(512))

    # values_callable: without it, SQLAlchemy's Enum type binds/reads the
    # Python member *name* ("ANNUAL_REPORT"), not its *value*
    # ("annual_report") — but the Postgres type was created by the Alembic
    # migration with the lowercase values. The mismatch is invisible in
    # tests that build the schema via `Base.metadata.create_all()` (which
    # would create the enum type using names too, so it's self-consistent)
    # and only breaks against a real, migration-created database.
    document_type: Mapped[DocumentType] = mapped_column(
        SAEnum(DocumentType, name="document_type", values_callable=lambda e: [m.value for m in e]),
        default=DocumentType.OTHER,
    )
    reporting_period: Mapped[str | None] = mapped_column(String(64))
    """Free-form period label, e.g. "2025" or "Q4 2025"."""

    source: Mapped[str | None] = mapped_column(String(512))
    """Where the document came from (URL, "user upload", etc.)."""

    status: Mapped[DocumentStatus] = mapped_column(
        SAEnum(
            DocumentStatus, name="document_status", values_callable=lambda e: [m.value for m in e]
        ),
        default=DocumentStatus.UPLOADED,
        index=True,
    )
    status_detail: Mapped[str | None] = mapped_column(Text)
    """Human-readable detail for the current status, e.g. an error message."""

    page_count: Mapped[int | None] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(String(1024))
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    """SHA-256 of the file content — used to detect/skip duplicate uploads."""

    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_duration_ms: Mapped[int | None] = mapped_column(Integer)

    company: Mapped["Company"] = relationship(back_populates="documents")  # noqa: F821
    # passive_deletes=True: rely on the FK's ondelete="CASCADE" (see
    # DocumentChunk.document_id) instead of SQLAlchemy loading the whole
    # chunk collection into memory before deleting each row one at a time.
    chunks: Mapped[list["DocumentChunk"]] = relationship(  # noqa: F821
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )
