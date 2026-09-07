"""Ingestion pipeline coordinator — runs entirely in the worker process,
never inline in an API request (Section 18).

    Upload -> Parsing -> Chunking -> Embedding -> Indexed

`process_document` is the single function that owns a document's status
transitions end to end, so there's exactly one place to look to understand
a document's lifecycle.
"""

import time
import uuid

from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.db.session import session_scope
from app.models.enums import DocumentStatus
from app.rag.embeddings.base import EmbeddingService
from app.rag.embeddings.factory import get_embedding_service
from app.rag.ingestion.document_parser import parse_document
from app.rag.ingestion.text_cleaner import clean_text
from app.services import document_service
from app.services.indexing_service import index_document
from app.services.job_queue import TaskState, set_task_status

logger = get_logger("ingestion")


async def process_document(
    document_id: uuid.UUID, embedding_service: EmbeddingService | None = None
) -> None:
    """`embedding_service` is injectable so tests can pass a fake instead
    of downloading a real model; production (the worker) leaves it unset
    and gets the shared Hugging Face singleton."""
    embedding_service = embedding_service or get_embedding_service()
    started = time.monotonic()
    await set_task_status(document_id, TaskState.RUNNING, stage="parsing")

    try:
        async with session_scope() as db:
            document = await document_service.get_document(db, document_id)
            await document_service.update_document_status(
                db, document_id, DocumentStatus.PARSING
            )
            file_path = document.file_path
            extension = "." + document.filename.rsplit(".", 1)[-1].lower()

        parsed = parse_document(file_path, extension)
        pages = [(p.page_number, clean_text(p.text)) for p in parsed.pages]
        logger.info(
            "ingestion.parsed",
            document_id=str(document_id),
            page_count=parsed.page_count,
            char_count=sum(len(t) for _, t in pages),
        )

        async with session_scope() as db:
            await document_service.update_document_status(
                db, document_id, DocumentStatus.CHUNKING, page_count=parsed.page_count
            )

        await set_task_status(document_id, TaskState.RUNNING, stage="embedding")
        async with session_scope() as db:
            await document_service.update_document_status(
                db, document_id, DocumentStatus.EMBEDDING
            )
            document = await document_service.get_document(db, document_id)
            chunk_count = await index_document(db, document, pages, embedding_service)

            duration_ms = int((time.monotonic() - started) * 1000)
            await document_service.update_document_status(
                db,
                document_id,
                DocumentStatus.INDEXED,
                chunk_count=chunk_count,
                processing_duration_ms=duration_ms,
            )
        logger.info(
            "ingestion.indexed",
            document_id=str(document_id),
            chunk_count=chunk_count,
            duration_ms=duration_ms,
        )
        await set_task_status(document_id, TaskState.COMPLETED, stage="indexed")

    except AppError as exc:
        logger.warning("ingestion.failed", document_id=str(document_id), error=exc.message)
        async with session_scope() as db:
            await document_service.update_document_status(
                db, document_id, DocumentStatus.FAILED, detail=exc.message
            )
        await set_task_status(document_id, TaskState.FAILED, stage="failed", detail=exc.message)

    except Exception as exc:  # noqa: BLE001 - last line of defense (Section 32)
        logger.exception("ingestion.unexpected_error", document_id=str(document_id))
        async with session_scope() as db:
            await document_service.update_document_status(
                db, document_id, DocumentStatus.FAILED, detail=f"Unexpected error: {exc}"
            )
        await set_task_status(document_id, TaskState.FAILED, stage="failed", detail=str(exc))
