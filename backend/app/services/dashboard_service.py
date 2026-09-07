"""Aggregates the numbers the `/dashboard` page (Section 3) shows. Reads
across `documents`, `companies`, `document_chunks`, `analyses`, and the
Redis cache-stats counters (Section 17) — nothing here is hardcoded demo
data (Section 40).
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.analysis import Analysis
from app.models.company import Company
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.schemas.dashboard import DashboardStats
from app.schemas.document import DocumentRead
from app.services.cache_service import get_cache_stats


async def get_dashboard_stats(db: AsyncSession) -> DashboardStats:
    documents_total = (await db.execute(select(func.count()).select_from(Document))).scalar_one()
    companies_total = (await db.execute(select(func.count()).select_from(Company))).scalar_one()
    embeddings_total = (
        await db.execute(select(func.count()).select_from(DocumentChunk))
    ).scalar_one()
    indexed_pages_total = (
        await db.execute(select(func.coalesce(func.sum(Document.page_count), 0)))
    ).scalar_one()
    analyses_total = (await db.execute(select(func.count()).select_from(Analysis))).scalar_one()

    status_rows = await db.execute(
        select(Document.status, func.count()).group_by(Document.status)
    )
    documents_by_status = {status.value: count for status, count in status_rows.all()}

    avg_latency = (
        await db.execute(select(func.avg(Analysis.execution_time_ms)))
    ).scalar_one()

    cache_stats = await get_cache_stats()

    recent_documents_result = await db.execute(
        select(Document)
        .order_by(Document.created_at.desc())
        .limit(5)
        .options(selectinload(Document.company))
    )
    recent_documents = recent_documents_result.scalars().all()

    recent_analyses_result = await db.execute(
        select(Analysis.query).order_by(Analysis.created_at.desc()).limit(5)
    )
    recent_analysis_queries = list(recent_analyses_result.scalars().all())

    return DashboardStats(
        documents_total=documents_total,
        companies_total=companies_total,
        indexed_pages_total=int(indexed_pages_total or 0),
        embeddings_total=embeddings_total,
        analyses_total=analyses_total,
        documents_by_status=documents_by_status,
        avg_query_latency_ms=float(avg_latency) if avg_latency is not None else None,
        cache_hit_rate=cache_stats["hit_rate"],
        cache_hits=cache_stats["hits"],
        cache_misses=cache_stats["misses"],
        recent_documents=[DocumentRead.model_validate(d) for d in recent_documents],
        recent_analysis_queries=recent_analysis_queries,
    )
