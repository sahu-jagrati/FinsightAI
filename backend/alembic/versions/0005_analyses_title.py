"""analyses.title

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-15

Research History (Recent Research) feature: a short, stable label for
each persisted analysis, derived from its query at persist time. Added
as nullable + backfilled so it plays nicely with rows that already exist
from earlier real-data testing, then tightened to NOT NULL.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("analyses", sa.Column("title", sa.String(length=200), nullable=True))
    # Backfill existing rows (truncate to 200 chars, same as the app's
    # generation heuristic) before tightening the constraint.
    op.execute("UPDATE analyses SET title = left(query, 200) WHERE title IS NULL")
    op.alter_column("analyses", "title", nullable=False)


def downgrade() -> None:
    op.drop_column("analyses", "title")
