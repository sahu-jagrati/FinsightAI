"""enable pgvector + full-text-search extensions

Revision ID: 0001
Revises:
Create Date: 2026-09-02

Establishes the Postgres extensions the rest of the schema depends on:
- vector: dense embedding storage/search (pgvector), used starting Phase 3.
- pg_trgm: trigram similarity, useful for fuzzy company/ticker lookups.
- unaccent: normalizes text for full-text search (Phase 5 hybrid search).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS unaccent")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS vector")
