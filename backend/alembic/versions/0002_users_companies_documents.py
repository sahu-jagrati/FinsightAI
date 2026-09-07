"""users, companies, documents

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-03

Phase 2: document upload + PDF parsing. Adds the three tables the upload
pipeline needs before any chunk/embedding exists.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# create_type=False: we create/drop these types ourselves (explicitly,
# with checkfirst) below. Without it, SQLAlchemy ALSO tries to auto-create
# the type as part of `create_table`'s own DDL (it fires a `before_create`
# event for every Enum-typed column), which collides with our explicit
# `.create()` call and fails with "type already exists".
document_type_enum = postgresql.ENUM(
    "annual_report",
    "quarterly_report",
    "sec_filing",
    "earnings_report",
    "news",
    "other",
    name="document_type",
    create_type=False,
)
document_status_enum = postgresql.ENUM(
    "uploaded",
    "parsing",
    "chunking",
    "embedding",
    "indexed",
    "failed",
    name="document_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    document_type_enum.create(bind, checkfirst=True)
    document_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("ticker", sa.String(16), nullable=True),
        sa.Column("industry", sa.String(255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("name", name="uq_companies_name"),
    )
    op.create_index("ix_companies_name", "companies", ["name"])
    op.create_index("ix_companies_ticker", "companies", ["ticker"])

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("document_type", document_type_enum, nullable=False, server_default="other"),
        sa.Column("reporting_period", sa.String(64), nullable=True),
        sa.Column("source", sa.String(512), nullable=True),
        sa.Column("status", document_status_enum, nullable=False, server_default="uploaded"),
        sa.Column("status_detail", sa.Text, nullable=True),
        sa.Column("page_count", sa.Integer, nullable=True),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("file_size_bytes", sa.Integer, nullable=True),
        sa.Column("file_path", sa.String(1024), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_duration_ms", sa.Integer, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_documents_company_id", "documents", ["company_id"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"])


def downgrade() -> None:
    op.drop_table("documents")
    op.drop_table("companies")
    op.drop_table("users")
    document_status_enum.drop(op.get_bind(), checkfirst=True)
    document_type_enum.drop(op.get_bind(), checkfirst=True)
