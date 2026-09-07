import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import DocumentStatus, DocumentType
from app.schemas.company import CompanyRead


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company: CompanyRead | None
    original_filename: str
    document_type: DocumentType
    reporting_period: str | None
    source: str | None
    status: DocumentStatus
    status_detail: str | None
    page_count: int | None
    chunk_count: int
    file_size_bytes: int | None
    processing_duration_ms: int | None
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentRead]
    total: int
    limit: int
    offset: int
