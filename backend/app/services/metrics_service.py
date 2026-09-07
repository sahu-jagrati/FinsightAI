"""Reads for `financial_metrics` — the Financial Extraction Agent's
persisted output (Section 12/21)."""

import uuid
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.financial_metric import FinancialMetric
from app.schemas.metrics import MetricSeries


async def list_metrics(
    db: AsyncSession,
    *,
    company_id: uuid.UUID | None = None,
    metric_name: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[FinancialMetric], int]:
    stmt = select(FinancialMetric)
    count_stmt = select(func.count()).select_from(FinancialMetric)
    if company_id is not None:
        stmt = stmt.where(FinancialMetric.company_id == company_id)
        count_stmt = count_stmt.where(FinancialMetric.company_id == company_id)
    if metric_name is not None:
        stmt = stmt.where(FinancialMetric.metric_name == metric_name)
        count_stmt = count_stmt.where(FinancialMetric.metric_name == metric_name)

    stmt = stmt.order_by(FinancialMetric.year.desc().nulls_last()).limit(limit).offset(offset)
    total = (await db.execute(count_stmt)).scalar_one()
    items = (await db.execute(stmt)).scalars().all()
    return list(items), total


async def get_company_metric_series(
    db: AsyncSession, company_id: uuid.UUID
) -> list[MetricSeries]:
    result = await db.execute(
        select(FinancialMetric)
        .where(FinancialMetric.company_id == company_id, FinancialMetric.year.is_not(None))
        .order_by(FinancialMetric.year)
    )
    rows = result.scalars().all()

    grouped: dict[str, list[FinancialMetric]] = defaultdict(list)
    for row in rows:
        grouped[row.metric_name].append(row)

    series: list[MetricSeries] = []
    for metric_name, metric_rows in grouped.items():
        # One point per year — highest-confidence extraction wins if a
        # year has more than one (e.g. mentioned in two different chunks).
        best_by_year: dict[int, FinancialMetric] = {}
        for row in metric_rows:
            existing = best_by_year.get(row.year)
            if existing is None or row.confidence > existing.confidence:
                best_by_year[row.year] = row

        points = [
            {"year": year, "value": row.value}
            for year, row in sorted(best_by_year.items())
        ]
        series.append(
            MetricSeries(metric_name=metric_name, unit=metric_rows[0].unit, points=points)
        )

    return series
