"""document_chunks — pgvector embeddings + full-text search

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-03

Phase 3: chunking + embeddings + pgvector. One table serves both retrieval
paths (Section 8):
  - dense: HNSW index over `embedding` (cosine distance)
  - sparse: GIN index over `to_tsvector('english', content)`, computed at
    query time rather than stored, since Postgres can index a functional
    expression directly — no generated column needed.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from app.core.config import settings

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=False),
        sa.Column("page_number", sa.Integer, nullable=True),
        sa.Column("section", sa.String(255), nullable=True),
        sa.Column("document_type", sa.String(64), nullable=True),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column(
            "chunk_metadata", postgresql.JSONB, nullable=False, server_default="{}"
        ),
        sa.Column("embedding", Vector(settings.EMBEDDING_DIMENSIONS), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_document_chunks_company_id", "document_chunks", ["company_id"])
    op.create_index("ix_document_chunks_page_number", "document_chunks", ["page_number"])
    op.create_index("ix_document_chunks_section", "document_chunks", ["section"])
    op.create_index("ix_document_chunks_document_type", "document_chunks", ["document_type"])
    op.create_index("ix_document_chunks_year", "document_chunks", ["year"])

    # Dense retrieval: HNSW over cosine distance. `vector_cosine_ops` matches
    # the `<=>` operator used in vector_store.py's similarity queries.
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_hnsw "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
    )

    # Sparse retrieval: functional GIN index over English full-text search.
    op.execute(
        "CREATE INDEX ix_document_chunks_content_fts "
        "ON document_chunks USING GIN (to_tsvector('english', content))"
    )


def downgrade() -> None:
    op.drop_table("document_chunks")
