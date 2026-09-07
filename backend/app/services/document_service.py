"""Document + company persistence (Section 29: business logic lives in
services, not route handlers).
"""

import uuid
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.models.company import Company
from app.models.document import Document
from app.models.enums import DocumentStatus, DocumentType


async def get_or_create_company(
    db: AsyncSession, name: str, *, ticker: str | None = None, industry: str | None = None
) -> Company:
    name = name.strip()
    result = await db.execute(select(Company).where(func.lower(Company.name) == name.lower()))
    company = result.scalar_one_or_none()
    if company:
        return company

    company = Company(name=name, ticker=ticker, industry=industry)
    db.add(company)
    await db.flush()
    return company


async def create_document(
    db: AsyncSession,
    *,
    company: Company | None,
    filename: str,
    original_filename: str,
    file_path: str,
    file_size_bytes: int,
    content_hash: str,
    document_type: DocumentType,
    reporting_period: str | None,
    source: str | None,
) -> Document:
    document = Document(
        company_id=company.id if company else None,
        filename=filename,
        original_filename=original_filename,
        file_path=file_path,
        file_size_bytes=file_size_bytes,
        content_hash=content_hash,
        document_type=document_type,
        reporting_period=reporting_period,
        source=source,
        status=DocumentStatus.UPLOADED,
    )
    db.add(document)
    await db.flush()
    await db.refresh(document, attribute_names=["company"])
    return document


async def get_document(db: AsyncSession, document_id: uuid.UUID) -> Document:
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.company))
        .where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise NotFoundError(f"Document {document_id} not found.")
    return document


async def list_documents(
    db: AsyncSession,
    *,
    company_id: uuid.UUID | None = None,
    document_type: DocumentType | None = None,
    status: DocumentStatus | None = None,
    search: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Document], int]:
    filters = []
    if company_id is not None:
        filters.append(Document.company_id == company_id)
    if document_type is not None:
        filters.append(Document.document_type == document_type)
    if status is not None:
        filters.append(Document.status == status)
    if search:
        like = f"%{search.lower()}%"
        filters.append(func.lower(Document.original_filename).like(like))

    count_stmt = select(func.count()).select_from(Document)
    list_stmt = (
        select(Document)
        .options(selectinload(Document.company))
        .order_by(Document.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    for f in filters:
        count_stmt = count_stmt.where(f)
        list_stmt = list_stmt.where(f)

    total = (await db.execute(count_stmt)).scalar_one()
    items = (await db.execute(list_stmt)).scalars().all()
    return list(items), total


async def delete_document(db: AsyncSession, document_id: uuid.UUID) -> None:
    document = await get_document(db, document_id)
    file_path = Path(document.file_path)
    await db.delete(document)
    await db.flush()
    if file_path.exists():
        file_path.unlink(missing_ok=True)


async def update_document_status(
    db: AsyncSession,
    document_id: uuid.UUID,
    status: DocumentStatus,
    *,
    detail: str | None = None,
    page_count: int | None = None,
    chunk_count: int | None = None,
    processing_duration_ms: int | None = None,
) -> Document:
    document = await get_document(db, document_id)
    document.status = status
    if detail is not None:
        document.status_detail = detail
    if page_count is not None:
        document.page_count = page_count
    if chunk_count is not None:
        document.chunk_count = chunk_count
    if processing_duration_ms is not None:
        document.processing_duration_ms = processing_duration_ms
    await db.flush()
    return document
