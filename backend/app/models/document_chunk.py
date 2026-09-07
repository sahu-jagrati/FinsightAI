"""document_chunks table (Section 6/20) — the unit of retrieval.

Postgres-only: `embedding` uses pgvector's `Vector` type, and full-text
search runs against `to_tsvector('english', content)` computed at query
time (indexed via a functional GIN index created in the migration — see
`alembic/versions/0003_*.py`) rather than a second mapped tsvector column.
That keeps this model simple and is why `document_chunks` is excluded from
the SQLite table set the test suite builds (see `tests/conftest.py`);
retrieval/hybrid-search tests run against a real Postgres instead (skipped
when one isn't available, same pattern as the Redis tests).
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.types import GUID


class DocumentChunk(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "document_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="SET NULL"), index=True
    )

    chunk_index: Mapped[int] = mapped_column(Integer)
    """Order of this chunk within its document (0-based)."""

    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)

    page_number: Mapped[int | None] = mapped_column(Integer, index=True)
    section: Mapped[str | None] = mapped_column(String(255), index=True)

    # Denormalized filter columns (Section 7: metadata filtering by
    # company/year/document type without a join) plus a JSONB bag for
    # anything else worth keeping per-chunk (Section 6's example: source,
    # filename, subsection...).
    document_type: Mapped[str | None] = mapped_column(String(64), index=True)
    year: Mapped[int | None] = mapped_column(Integer, index=True)
    chunk_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)

    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.EMBEDDING_DIMENSIONS), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped["Document"] = relationship(back_populates="chunks")  # noqa: F821
