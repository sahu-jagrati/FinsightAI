"""companies table (Section 20) — the entity documents, financial metrics,
and comparison-agent queries all key off.
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    ticker: Mapped[str | None] = mapped_column(String(16), index=True)
    industry: Mapped[str | None] = mapped_column(String(255))

    documents: Mapped[list["Document"]] = relationship(  # noqa: F821
        back_populates="company", cascade="all, delete-orphan"
    )
