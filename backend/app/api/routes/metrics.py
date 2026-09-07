import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.metrics import FinancialMetricRead, MetricSeries
from app.services import metrics_service

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_model=list[FinancialMetricRead])
async def list_metrics(
    company_id: uuid.UUID | None = None,
    metric_name: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> list[FinancialMetricRead]:
    limit = max(1, min(limit, 200))
    items, _total = await metrics_service.list_metrics(
        db, company_id=company_id, metric_name=metric_name, limit=limit, offset=offset
    )
    return [FinancialMetricRead.model_validate(m) for m in items]


@router.get("/companies/{company_id}/metrics", response_model=list[MetricSeries])
async def get_company_metrics(
    company_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[MetricSeries]:
    return await metrics_service.get_company_metric_series(db, company_id)
