import pytest

from app.models.document_chunk import DocumentChunk
from app.rag.retrieval.reranker import IdentityReranker
from app.rag.retrieval.vector_store import ScoredChunk
from tests.fakes import FakeReranker

pytestmark = pytest.mark.asyncio


def _scored(content: str) -> ScoredChunk:
    chunk = DocumentChunk(content=content, chunk_index=0, token_count=len(content.split()))
    return ScoredChunk(chunk=chunk)


async def test_identity_reranker_truncates_without_reordering():
    candidates = [_scored("a"), _scored("b"), _scored("c")]
    result = await IdentityReranker().rerank("query", candidates, top_n=2)
    assert result == candidates[:2]


async def test_fake_reranker_ranks_by_word_overlap():
    candidates = [
        _scored("completely unrelated text about weather"),
        _scored("Apple iPhone revenue grew significantly"),
    ]
    result = await FakeReranker().rerank("Apple iPhone revenue", candidates, top_n=2)
    assert result[0].chunk.content.startswith("Apple")
