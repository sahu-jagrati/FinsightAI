"""vector_store — pgvector-backed chunk storage + dense (cosine) search
(Section 7).

Cosine similarity, spelled out for the record:

    similarity(A, B) = (A . B) / (||A|| ||B||)

pgvector's `<=>` operator computes cosine *distance* = 1 - similarity
directly in the database (using the HNSW index from migration 0003), so
`1 - embedding.cosine_distance(query)` below IS that formula — just
evaluated by Postgres instead of Python, which is what makes top-k search
over millions of rows fast.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_chunk import DocumentChunk
from app.rag.ingestion.chunker import Chunk


@dataclass
class RetrievalFilters:
    company_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    document_type: str | None = None
    year: int | None = None
    years: list[int] | None = None


@dataclass
class ScoredChunk:
    chunk: DocumentChunk
    dense_score: float = 0.0
    sparse_score: float = 0.0
    final_score: float = 0.0
    rerank_score: float | None = None


def apply_filters(stmt, filters: RetrievalFilters | None):
    if filters is None:
        return stmt
    if filters.company_id is not None:
        stmt = stmt.where(DocumentChunk.company_id == filters.company_id)
    if filters.document_id is not None:
        stmt = stmt.where(DocumentChunk.document_id == filters.document_id)
    if filters.document_type is not None:
        stmt = stmt.where(DocumentChunk.document_type == filters.document_type)
    # `year` is denormalized from the *document's* `reporting_period` at
    # ingestion time (one value for the whole document — see
    # `metadata_extractor.extract_year` / `indexing_service.index_document`)
    # — it's often unset entirely (an upload with no reporting_period
    # given), and even when set it doesn't mean "this chunk only discusses
    # that year": a 10-K's financial-statement/segment tables routinely
    # report 2-3 fiscal years' figures side by side in the SAME chunk (e.g.
    # "Total net sales $416,161 ... $391,035 ..." is one chunk covering
    # both FY2025 and FY2024). Treating a query's requested year(s) as a
    # hard `WHERE year = ...` exclusion previously threw away exactly the
    # right evidence for any document missing/mismatching that one coarse
    # value — reproduced live against a real uploaded Apple 10-K PDF with
    # no reporting_period set (year IS NULL on every one of its chunks):
    # `year IN (2024, 2025)` matched zero rows, while the unfiltered
    # search's #1 result (dense score 0.80) was the exact "Total net
    # sales" chunk containing both requested years. So `year`, when
    # present, is used only to prefer/narrow among chunks that HAVE it —
    # it never excludes a chunk that doesn't carry that metadata.
    if filters.year is not None:
        stmt = stmt.where(or_(DocumentChunk.year.is_(None), DocumentChunk.year == filters.year))
    if filters.years:
        stmt = stmt.where(or_(DocumentChunk.year.is_(None), DocumentChunk.year.in_(filters.years)))
    return stmt


async def insert_chunks(
    db: AsyncSession,
    *,
    document_id: uuid.UUID,
    company_id: uuid.UUID | None,
    document_type: str | None,
    year: int | None,
    source: str | None,
    filename: str | None,
    chunks: list[Chunk],
    embeddings: list[list[float]],
) -> list[DocumentChunk]:
    if len(chunks) != len(embeddings):
        raise ValueError("chunks and embeddings must be the same length")

    rows: list[DocumentChunk] = []
    for chunk, embedding in zip(chunks, embeddings, strict=True):
        rows.append(
            DocumentChunk(
                document_id=document_id,
                company_id=company_id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                token_count=chunk.token_count,
                page_number=chunk.page_number,
                section=chunk.section,
                document_type=document_type,
                year=year,
                chunk_metadata={"source": source, "filename": filename},
                embedding=embedding,
            )
        )
    db.add_all(rows)
    await db.flush()
    return rows


async def dense_search(
    db: AsyncSession,
    query_embedding: list[float],
    *,
    top_k: int,
    filters: RetrievalFilters | None = None,
) -> list[ScoredChunk]:
    distance = DocumentChunk.embedding.cosine_distance(query_embedding)
    stmt = select(DocumentChunk, distance.label("distance")).where(
        DocumentChunk.embedding.is_not(None)
    )
    stmt = apply_filters(stmt, filters).order_by(distance).limit(top_k)

    result = await db.execute(stmt)
    return [
        ScoredChunk(chunk=chunk, dense_score=max(0.0, 1.0 - distance))
        for chunk, distance in result.all()
    ]
