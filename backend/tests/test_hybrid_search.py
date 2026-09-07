"""Postgres-only (see `pg_session` in conftest.py)."""

import pytest

from app.models.company import Company
from app.models.document import Document
from app.models.enums import DocumentType
from app.rag.ingestion.chunker import Chunk
from app.rag.retrieval.hybrid_search import hybrid_search, sparse_search
from app.rag.retrieval.vector_store import insert_chunks
from tests.fakes import FakeEmbeddingService

pytestmark = pytest.mark.asyncio

embedder = FakeEmbeddingService()


async def _seed(db):
    company = Company(name="Apple")
    db.add(company)
    await db.flush()
    document = Document(
        company_id=company.id,
        filename="f.pdf",
        original_filename="f.pdf",
        document_type=DocumentType.ANNUAL_REPORT,
        file_path="/tmp/f.pdf",
    )
    db.add(document)
    await db.flush()

    texts = [
        "Apple's total revenue for fiscal 2025 was $400 billion.",
        "Net income margin improved due to cost discipline.",
        "The iPhone remains Apple's largest product category by revenue.",
    ]
    chunks = [
        Chunk(chunk_index=i, content=t, page_number=1, section=None, token_count=len(t.split()))
        for i, t in enumerate(texts)
    ]
    embeddings = await embedder.embed_documents(texts)
    await insert_chunks(
        db,
        document_id=document.id,
        company_id=company.id,
        document_type=document.document_type.value,
        year=2025,
        source="test",
        filename="f.pdf",
        chunks=chunks,
        embeddings=embeddings,
    )
    await db.commit()
    return company, document


async def test_sparse_search_finds_keyword_match(pg_session):
    await _seed(pg_session)
    results = await sparse_search(pg_session, "revenue fiscal 2025", top_k=5)
    assert any("400 billion" in r.chunk.content for r in results)


async def test_hybrid_search_combines_dense_and_sparse(pg_session):
    await _seed(pg_session)
    results = await hybrid_search(pg_session, "Apple total revenue", embedder, top_k=3)

    assert len(results) > 0
    assert all(r.final_score >= 0 for r in results)
    # results should be sorted descending by final_score
    scores = [r.final_score for r in results]
    assert scores == sorted(scores, reverse=True)


async def test_hybrid_search_alpha_zero_ranks_by_sparse_only(pg_session):
    await _seed(pg_session)
    results = await hybrid_search(pg_session, "revenue", embedder, top_k=3, alpha=0.0)

    ids_by_final_score = [r.chunk.id for r in results]
    ids_by_sparse_score = [
        r.chunk.id for r in sorted(results, key=lambda r: r.sparse_score, reverse=True)
    ]
    assert ids_by_final_score == ids_by_sparse_score
