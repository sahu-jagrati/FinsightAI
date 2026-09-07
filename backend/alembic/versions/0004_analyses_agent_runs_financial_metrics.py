"""analyses, agent_runs, financial_metrics

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-03

Phase 7/8: multi-agent architecture. `analyses` + `agent_runs` persist
every research query and its agent trace (Section 25); `financial_metrics`
holds structured numbers the Financial Extraction Agent pulls out of
retrieved chunks (Section 12).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# create_type=False: created/dropped explicitly below (with checkfirst) —
# see the comment on the same pattern in 0002_users_companies_documents.py.
analysis_status_enum = postgresql.ENUM(
    "pending", "running", "completed", "failed", name="analysis_status", create_type=False
)
agent_run_status_enum = postgresql.ENUM(
    "waiting", "running", "completed", "failed", name="agent_run_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    analysis_status_enum.create(bind, checkfirst=True)
    agent_run_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("status", analysis_status_enum, nullable=False, server_default="pending"),
        sa.Column("result", postgresql.JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("execution_time_ms", sa.Integer, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_analyses_user_id", "analyses", ["user_id"])
    op.create_index("ix_analyses_status", "analyses", ["status"])

    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("status", agent_run_status_enum, nullable=False, server_default="waiting"),
        sa.Column("step_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("input", postgresql.JSONB, nullable=True),
        sa.Column("output", postgresql.JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("cache_hit", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("execution_time_ms", sa.Integer, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_agent_runs_analysis_id", "agent_runs", ["analysis_id"])
    op.create_index("ix_agent_runs_agent_name", "agent_runs", ["agent_name"])

    op.create_table(
        "financial_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_chunks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("metric_name", sa.String(64), nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("period", sa.String(64), nullable=False),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("source_page", sa.Integer, nullable=True),
        sa.Column("confidence", sa.Float, nullable=False, server_default="1.0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_financial_metrics_company_id", "financial_metrics", ["company_id"])
    op.create_index("ix_financial_metrics_document_id", "financial_metrics", ["document_id"])
    op.create_index("ix_financial_metrics_metric_name", "financial_metrics", ["metric_name"])
    op.create_index("ix_financial_metrics_year", "financial_metrics", ["year"])


def downgrade() -> None:
    op.drop_table("financial_metrics")
    op.drop_table("agent_runs")
    op.drop_table("analyses")
    agent_run_status_enum.drop(op.get_bind(), checkfirst=True)
    analysis_status_enum.drop(op.get_bind(), checkfirst=True)
