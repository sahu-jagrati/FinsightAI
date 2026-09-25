"""Unit tests for the Retrieval Agent's cross-company fairness logic.

`hybrid_search` and company-name resolution are monkeypatched so this runs
without a real Postgres — the actual dense/sparse SQL is already covered
by `test_hybrid_search.py` (Postgres-only). What's under test here is pure
Python: does the agent give every company in a comparison query a fair
share of the final evidence, or can one company's higher cross-encoder
scores crowd the other out entirely?
"""

import uuid

import pytest

import app.agents.retrieval_agent as retrieval_agent_module
from app.agents.retrieval_agent import _normalized_score, run_retrieval_agent
from app.agents.state import QueryUnderstanding, ResearchState
from app.models.document_chunk import DocumentChunk
from app.rag.retrieval.reranker import IdentityReranker
from app.rag.retrieval.vector_store import ScoredChunk


def test_normalized_score_maps_negative_rerank_logit_into_zero_to_one():
    """Regression test for a real bug: a cross-encoder's raw `rerank_score`
    is an unbounded logit (often negative for a merely-plausible, not
    bad, match) — using it directly as a [0,1] confidence silently
    collapsed legitimate evidence to confidence 0.0 for a real "what are
    the risks" query."""
    negative_logit_chunk = ScoredChunk(chunk=None, final_score=0.6, rerank_score=-1.4)
    score = _normalized_score(negative_logit_chunk)
    assert 0.0 < score < 1.0

    positive_logit_chunk = ScoredChunk(chunk=None, final_score=0.6, rerank_score=3.0)
    assert _normalized_score(positive_logit_chunk) > 0.9

    no_rerank_chunk = ScoredChunk(chunk=None, final_score=0.75, rerank_score=None)
    assert _normalized_score(no_rerank_chunk) == 0.75


class _NullAsyncContextManager:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc_info):
        return False


def _chunk(content: str, score: float) -> ScoredChunk:
    doc_chunk = DocumentChunk(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        company_id=None,  # keeps the test from needing a real company lookup
        chunk_index=0,
        content=content,
        token_count=len(content.split()),
        page_number=1,
        chunk_metadata={"filename": "f.pdf"},
    )
    return ScoredChunk(chunk=doc_chunk, final_score=score)


@pytest.mark.asyncio
async def test_comparison_query_gives_each_company_a_fair_evidence_share(monkeypatch):
    """Regression test for a real bug found comparing Apple vs. Microsoft:
    reranking the two companies' pooled candidates together with one flat
    top_n cutoff let Microsoft's higher-scoring chunks fill every slot,
    leaving zero Apple evidence — silently turning a comparison query into
    a single-company answer."""

    resolved = {"Apple": uuid.uuid4(), "Microsoft": uuid.uuid4()}

    async def fake_resolve_company_ids(state):
        return resolved

    async def fake_hybrid_search(session, query, embedding_service, *, filters=None, **kw):
        # Microsoft returns MORE candidates, all higher-scoring, than the
        # global RERANK_TOP_N budget alone — with a single flat rerank
        # across the pooled set (the bug), all 5 slots go to Microsoft and
        # Apple's one (lower-scoring but real) chunk is excluded entirely.
        if filters and filters.company_id == resolved["Apple"]:
            return [_chunk("Apple revenue was $416B.", 0.2)]
        return [_chunk(f"Microsoft revenue chunk {i}.", 0.9 - i * 0.01) for i in range(5)]

    monkeypatch.setattr(retrieval_agent_module, "_resolve_company_ids", fake_resolve_company_ids)
    monkeypatch.setattr(retrieval_agent_module, "hybrid_search", fake_hybrid_search)
    # Don't let a real (or previously-run) Redis cache short-circuit the
    # fake search this test depends on — this test cares about the
    # allocation logic, not caching, which has its own tests.
    async def _no_cache_hit(*a, **kw):
        return None

    async def _noop_cache_set(*a, **kw):
        return None

    monkeypatch.setattr(retrieval_agent_module, "cache_get_json", _no_cache_hit)
    monkeypatch.setattr(retrieval_agent_module, "cache_set_json", _noop_cache_set)

    state = ResearchState(
        query="Compare Apple's and Microsoft's revenue growth.",
        db=None,
        llm=None,
        embedding_service=None,
        reranker=IdentityReranker(),
        session_factory=_NullAsyncContextManager,
        understanding=QueryUnderstanding(companies=["Apple", "Microsoft"], is_comparison=True),
    )

    await run_retrieval_agent(state)

    companies_represented = {item.content for item in state.evidence}
    assert any("Apple" in c for c in companies_represented)
    assert any("Microsoft" in c for c in companies_represented)
