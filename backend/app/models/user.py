"""users table (Section 20).

No login flow exists yet — the UI is single-tenant for now — but the column
is in place so `analyses.user_id` has somewhere real to point, and adding
auth later doesn't require a migration that touches every table that
references a user.
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
