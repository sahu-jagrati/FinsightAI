"""Document management endpoints (Section 4/19).

Upload never blocks on parsing/chunking/embedding — it saves the file,
writes a `documents` row, pushes a job onto the Redis ingestion queue, and
returns immediately. The worker process (`app/workers/ingestion.py`) does
the actual work and updates `status` as it progresses.
"""

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.enums import DocumentType
from app.rag.ingestion.document_loader import save_upload
from app.schemas.document import DocumentListResponse, DocumentRead
from app.services import document_service
from app.services.job_queue import enqueue_ingestion_job

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    company_name: str | None = Form(default=None),
    document_type: DocumentType = Form(default=DocumentType.OTHER),
    reporting_period: str | None = Form(default=None),
    source: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
) -> DocumentRead:
    loaded = await save_upload(file)

    company = None
    if company_name:
        company = await document_service.get_or_create_company(db, company_name)

    document = await document_service.create_document(
        db,
        company=company,
        filename=loaded.stored_filename,
        original_filename=loaded.original_filename,
        file_path=loaded.file_path,
        file_size_bytes=loaded.file_size_bytes,
        content_hash=loaded.content_hash,
        document_type=document_type,
        reporting_period=reporting_period,
        source=source,
    )
    await db.commit()
    await db.refresh(document, attribute_names=["company"])

    await enqueue_ingestion_job(document.id)

    return DocumentRead.model_validate(document)


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    company_id: uuid.UUID | None = None,
    document_type: DocumentType | None = None,
    search: str | None = None,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    limit = max(1, min(limit, 100))
    items, total = await document_service.list_documents(
        db,
        company_id=company_id,
        document_type=document_type,
        search=search,
        limit=limit,
        offset=offset,
    )
    return DocumentListResponse(
        items=[DocumentRead.model_validate(d) for d in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(document_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> DocumentRead:
    document = await document_service.get_document(db, document_id)
    return DocumentRead.model_validate(document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    await document_service.delete_document(db, document_id)
    await db.commit()
