"""indexing_service — chunk -> embed -> store, the last three stages of
the ingestion pipeline (Section 5). Kept separate from
`app/rag/ingestion/pipeline.py` so it can be called directly (e.g. a future
re-index endpoint) without going through the full parse-from-disk flow.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.rag.embeddings.base import EmbeddingService
from app.rag.ingestion.chunker import PageLike, chunk_document
from app.rag.ingestion.metadata_extractor import extract_year
from app.rag.retrieval.vector_store import insert_chunks


async def index_document(
    db: AsyncSession,
    document: Document,
    pages: list[tuple[int, str]],
    embedding_service: EmbeddingService,
) -> int:
    """`pages` is (page_number, cleaned_text) pairs. Returns the number of
    chunks written."""
    chunks = chunk_document([PageLike(page_number=n, text=t) for n, t in pages])
    if not chunks:
        return 0

    embeddings = await embedding_service.embed_documents([c.content for c in chunks])

    await insert_chunks(
        db,
        document_id=document.id,
        company_id=document.company_id,
        document_type=document.document_type.value,
        year=extract_year(document.reporting_period),
        source=document.source,
        filename=document.original_filename,
        chunks=chunks,
        embeddings=embeddings,
    )
    return len(chunks)
