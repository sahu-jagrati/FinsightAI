"""Sparse (Postgres full-text) search + hybrid fusion with dense search
(Section 8).

    FinalScore = alpha * DenseScore + (1 - alpha) * SparseScore

Both `DenseScore` and `SparseScore` are min-max normalized to [0, 1] across
the candidate pool before fusing — they come from different scales
(cosine similarity vs. `ts_rank_cd`) and would otherwise let one signal
dominate regardless of `alpha`.
"""

import re
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


# Words that carry the *task* rather than the topic. In "What were Apple's
# total liabilities ... Calculate the percentage change and explain the
# reasons" nothing in a balance sheet contains "calculate", "percentage",
# "explain" or "reasons" — they'd only add noise to a keyword match.
_QUERY_TASK_WORDS = frozenset(
    "calculate calculated calculation percentage percent change changes explain reason reasons "
    "based only uploaded annual report fiscal year years what which compare comparison show tell "
    "give much many using according provide summarize summary main major "
    "a an the of to in on at by for with from as is are was were be been it its this that these "
    "those and or but not do does did has have had than then there their they you your".split()
)
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def query_topic_terms(query_text: str) -> list[str]:
    """The query's topical words (lowercased, de-duplicated, task words
    like "calculate"/"explain" removed) — shared by sparse search and the
    reranker's focused-excerpt selection so both agree on what the query is
    about."""
    seen: list[str] = []
    for token in _TOKEN_RE.findall(query_text.lower()):
        if len(token) < 2 or token in _QUERY_TASK_WORDS or token in seen:
            continue
        seen.append(token)
    return seen


def build_sparse_tsquery_text(query_text: str) -> str | None:
    """`term1 | term2 | ...` over the query's topical words, or None when
    nothing is left.

    `plainto_tsquery` ANDs every word, so a natural-language question
    ("What were Apple's total liabilities in fiscal year 2025 ... Calculate
    the percentage change ...") requires ONE chunk to contain all of them —
    which no real page does — and sparse search returned nothing at all,
    silently reducing "hybrid" retrieval to dense-only. That is what kept a
    10-K's balance sheet (a dense table, poorly served by embeddings) from
    ever being retrieved for a plain "total liabilities" question. An OR
    query lets `ts_rank_cd` do what it is for: rank chunks by how many, and
    how close together, the query's terms appear. Only `[A-Za-z0-9]` tokens
    are ever emitted, so the string is safe to hand to `to_tsquery`."""
    terms = query_topic_terms(query_text)
    return " | ".join(terms) if terms else None


async def sparse_search(
    db: AsyncSession,
    query_text: str,
    *,
    top_k: int,
    filters: RetrievalFilters | None = None,
) -> list[ScoredChunk]:
    tsquery_text = build_sparse_tsquery_text(query_text)
    if tsquery_text is None:
        return []
    tsquery = func.to_tsquery("english", tsquery_text)
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
