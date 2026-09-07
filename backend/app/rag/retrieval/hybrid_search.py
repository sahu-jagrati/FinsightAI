"""Sparse (Postgres full-text) search + hybrid fusion with dense search
(Section 8).

    FinalScore = alpha * DenseScore + (1 - alpha) * SparseScore

Both `DenseScore` and `SparseScore` are min-max normalized to [0, 1] across
the candidate pool before fusing — they come from different scales
(cosine similarity vs. `ts_rank_cd`) and would otherwise let one signal
dominate regardless of `alpha`.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document_chunk import DocumentChunk
from app.rag.embeddings.base import EmbeddingService
from app.rag.retrieval.vector_store import RetrievalFilters, ScoredChunk, apply_filters, dense_search

# Sparse search fetches a wider pool than the final top_k so fusion has
# enough candidates from each side to rank meaningfully (Section 8).
_CANDIDATE_POOL_MULTIPLIER = 4


async def sparse_search(
    db: AsyncSession,
    query_text: str,
    *,
    top_k: int,
    filters: RetrievalFilters | None = None,
) -> list[ScoredChunk]:
    tsquery = func.plainto_tsquery("english", query_text)
    tsvector = func.to_tsvector("english", DocumentChunk.content)
    rank = func.ts_rank_cd(tsvector, tsquery)

    stmt = select(DocumentChunk, rank.label("rank")).where(tsvector.op("@@")(tsquery))
    stmt = apply_filters(stmt, filters).order_by(rank.desc()).limit(top_k)

    result = await db.execute(stmt)
    return [ScoredChunk(chunk=chunk, sparse_score=float(rank)) for chunk, rank in result.all()]


def _min_max_normalize(scores: dict[uuid.UUID, float]) -> dict[uuid.UUID, float]:
    if not scores:
        return {}
    lo, hi = min(scores.values()), max(scores.values())
    if hi - lo < 1e-9:
        return dict.fromkeys(scores, 1.0 if hi > 0 else 0.0)
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


async def hybrid_search(
    db: AsyncSession,
    query_text: str,
    embedding_service: EmbeddingService,
    *,
    top_k: int | None = None,
    alpha: float | None = None,
    filters: RetrievalFilters | None = None,
) -> list[ScoredChunk]:
    top_k = top_k or settings.RETRIEVAL_TOP_K
    alpha = settings.HYBRID_SEARCH_ALPHA if alpha is None else alpha
    pool_size = top_k * _CANDIDATE_POOL_MULTIPLIER

    query_embedding = await embedding_service.embed_query(query_text)

    # Sequential, not `asyncio.gather` — both queries run on the same `db`
    # session, and a single AsyncSession cannot be used from two coroutines
    # concurrently (SQLAlchemy raises IllegalStateChangeError). Genuine
    # concurrency for retrieval happens one level up, across companies —
    # see the Retrieval Agent, which gives each concurrent branch its own
    # session via `state.session_factory` specifically so this is safe.
    dense_results = await dense_search(db, query_embedding, top_k=pool_size, filters=filters)
    sparse_results = await sparse_search(db, query_text, top_k=pool_size, filters=filters)

    dense_norm = _min_max_normalize({r.chunk.id: r.dense_score for r in dense_results})
    sparse_norm = _min_max_normalize({r.chunk.id: r.sparse_score for r in sparse_results})

    by_id: dict[uuid.UUID, ScoredChunk] = {}
    for r in dense_results:
        by_id[r.chunk.id] = r
    for r in sparse_results:
        if r.chunk.id in by_id:
            by_id[r.chunk.id].sparse_score = r.sparse_score
        else:
            by_id[r.chunk.id] = r

    for chunk_id, scored in by_id.items():
        d = dense_norm.get(chunk_id, 0.0)
        s = sparse_norm.get(chunk_id, 0.0)
        scored.final_score = alpha * d + (1 - alpha) * s

    ranked = sorted(by_id.values(), key=lambda r: r.final_score, reverse=True)
    return ranked[:top_k]
