"""financial_metrics table (Section 12/20) — structured numbers the
Financial Extraction Agent pulls out of retrieved chunks, always keeping
the source page so the Report Agent can cite it.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.types import GUID


class FinancialMetric(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "financial_metrics"

    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("document_chunks.id", ondelete="SET NULL")
    )

    metric_name: Mapped[str] = mapped_column(String(64), index=True)
    """e.g. revenue, net_income, operating_income, eps, total_assets,
    total_liabilities, operating_cash_flow, total_expenses, gross_margin,
    operating_margin, net_margin."""

    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(32))
    """e.g. usd, usd_millions, usd_billions, percent, ratio, usd_per_share."""

    period: Mapped[str] = mapped_column(String(64))
    year: Mapped[int | None] = mapped_column(Integer, index=True)

    source_page: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
