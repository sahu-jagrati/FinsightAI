import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FinancialMetricRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    document_id: uuid.UUID
    metric_name: str
    value: float
    unit: str
    period: str
    year: int | None
    source_page: int | None
    confidence: float
    created_at: datetime


class MetricSeries(BaseModel):
    metric_name: str
    unit: str
    points: list[dict]  # [{"year": 2024, "value": 383.0}, ...]
