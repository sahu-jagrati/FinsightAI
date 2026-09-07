"""Retrieval Agent (Section 11).

Understands what to search for from `state.understanding`, runs hybrid
search per company CONCURRENTLY when multiple companies are involved
(Section 31 — "Company A / Company B retrieval should execute
concurrently"), reranks the pooled candidates, and returns evidence with
enough provenance (document, page, section, score) for the Report Agent to
cite and for Section 16's confidence tracking.

Each concurrent branch opens its own session via `state.session_factory`
rather than sharing `state.db` — a single `AsyncSession` isn't safe to use
from more than one coroutine at once (SQLAlchemy raises
`IllegalStateChangeError` the moment two queries race on it), so real
concurrency here means real separate connections, not just separate
`asyncio` tasks contending for one.
"""

import asyncio
import uuid
from dataclasses import asdict

from sqlalchemy import select

from app.agents.state import EvidenceItem, ResearchState
from app.core.config import settings
from app.models.company import Company
from app.rag.retrieval.hybrid_search import hybrid_search
from app.rag.retrieval.vector_store import RetrievalFilters, ScoredChunk
from app.services.cache_service import cache_get_json, cache_set_json, make_cache_key

# Retrieval result caching (Section 17: "retrieval:{query_hash}") — skips
# re-embedding the query and re-running dense+sparse+rerank entirely for a
# question (and filters) seen recently.
_RETRIEVAL_CACHE_TTL_SECONDS = 600


def _evidence_to_cache(items: list[EvidenceItem]) -> list[dict]:
    return [
        {**asdict(item), "chunk_id": str(item.chunk_id), "document_id": str(item.document_id) if item.document_id else None, "company_id": str(item.company_id) if item.company_id else None}
        for item in items
    ]


def _evidence_from_cache(rows: list[dict]) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            chunk_id=uuid.UUID(r["chunk_id"]),
            content=r["content"],
            company=r["company"],
            document_filename=r["document_filename"],
            page_number=r["page_number"],
            section=r["section"],
            score=r["score"],
            document_id=uuid.UUID(r["document_id"]) if r["document_id"] else None,
            company_id=uuid.UUID(r["company_id"]) if r["company_id"] else None,
        )
        for r in rows
    ]


async def _resolve_company_ids(state: ResearchState) -> dict[str, object]:
    if not state.understanding.companies:
        return {}
    result = await state.db.execute(
        select(Company).where(Company.name.in_(state.understanding.companies))
    )
    return {c.name: c.id for c in result.scalars().all()}


def _build_filter_sets(
    company_name_to_id: dict[str, object], understanding
) -> list[tuple[str | None, RetrievalFilters]]:
    years = understanding.years or None
    document_type = understanding.document_types[0] if understanding.document_types else None

    if not company_name_to_id:
        return [(None, RetrievalFilters(document_type=document_type, years=years))]

    return [
        (name, RetrievalFilters(company_id=company_id, document_type=document_type, years=years))
        for name, company_id in company_name_to_id.items()
    ]


def _dedupe_keep_best(results: list[ScoredChunk]) -> list[ScoredChunk]:
    best: dict = {}
    for r in results:
        existing = best.get(r.chunk.id)
        if existing is None or r.final_score > existing.final_score:
            best[r.chunk.id] = r
    return list(best.values())


async def _search_with_own_session(
    state: ResearchState, filters: RetrievalFilters
) -> list[ScoredChunk]:
    """Runs one filter set's hybrid search on a dedicated session so
    multiple companies can genuinely search concurrently (see module
    docstring)."""
    async with state.session_factory() as session:
        return await hybrid_search(session, state.query, state.embedding_service, filters=filters)


async def run_retrieval_agent(state: ResearchState) -> None:
    trace = state.new_trace("retrieval_agent")
    trace.start(query=state.query, companies=state.understanding.companies)

    cache_key = make_cache_key(
        "retrieval",
        state.query.lower().strip(),
        sorted(state.understanding.companies),
        sorted(state.understanding.years),
        sorted(state.understanding.document_types),
        settings.RERANK_TOP_N,
    )

    try:
        cached = await cache_get_json(cache_key)
        if cached is not None:
            state.evidence = _evidence_from_cache(cached)
            trace.cache_hit = True
            trace.complete(evidence_count=len(state.evidence), cache_hit=True)
            return

        company_name_to_id = await _resolve_company_ids(state)
        filter_sets = _build_filter_sets(company_name_to_id, state.understanding)

        # Concurrent retrieval per company (Section 31) — each branch gets
        # its own session (see `_search_with_own_session`).
        result_groups = await asyncio.gather(
            *[_search_with_own_session(state, filters) for _, filters in filter_sets]
        )
        pooled = _dedupe_keep_best([r for group in result_groups for r in group])

        reranked = await state.reranker.rerank(state.query, pooled, top_n=settings.RERANK_TOP_N)

        company_ids = {r.chunk.company_id for r in reranked if r.chunk.company_id}
        id_to_name = {}
        if company_ids:
            rows = await state.db.execute(select(Company).where(Company.id.in_(company_ids)))
            id_to_name = {c.id: c.name for c in rows.scalars().all()}

        state.evidence = [
            EvidenceItem(
                chunk_id=r.chunk.id,
                content=r.chunk.content,
                company=id_to_name.get(r.chunk.company_id),
                document_filename=(r.chunk.chunk_metadata or {}).get("filename"),
                page_number=r.chunk.page_number,
                section=r.chunk.section,
                score=r.rerank_score if r.rerank_score is not None else r.final_score,
                document_id=r.chunk.document_id,
                company_id=r.chunk.company_id,
            )
            for r in reranked
        ]

        await cache_set_json(
            cache_key, _evidence_to_cache(state.evidence), _RETRIEVAL_CACHE_TTL_SECONDS
        )

        trace.complete(
            candidate_count=len(pooled),
            evidence_count=len(state.evidence),
            filter_sets=len(filter_sets),
        )
    except Exception as exc:  # noqa: BLE001
        trace.fail(str(exc))
        raise
