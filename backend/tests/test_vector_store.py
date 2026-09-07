"""Postgres-only (see `pg_session` in conftest.py — requires
TEST_DATABASE_URL, skipped otherwise)."""

import pytest

from app.models.company import Company
from app.models.document import Document
from app.models.enums import DocumentType
from app.rag.ingestion.chunker import Chunk
from app.rag.retrieval.vector_store import RetrievalFilters, dense_search, insert_chunks
from tests.fakes import FakeEmbeddingService

pytestmark = pytest.mark.asyncio

embedder = FakeEmbeddingService()


async def _make_document(db, *, company_name: str, document_type=DocumentType.ANNUAL_REPORT):
    company = Company(name=company_name)
    db.add(company)
    await db.flush()

    document = Document(
        company_id=company.id,
        filename="f.pdf",
        original_filename="f.pdf",
        document_type=document_type,
        file_path="/tmp/f.pdf",
    )
    db.add(document)
    await db.flush()
    return company, document


async def test_insert_and_dense_search_ranks_by_similarity(pg_session):
    company, document = await _make_document(pg_session, company_name="Apple")

    texts = [
        "Apple reported strong iPhone revenue growth this quarter.",
        "The weather in San Francisco was cloudy with light rain.",
        "Apple's services segment revenue also grew year over year.",
    ]
    chunks = [
        Chunk(chunk_index=i, content=t, page_number=1, section=None, token_count=len(t.split()))
        for i, t in enumerate(texts)
    ]
    embeddings = await embedder.embed_documents(texts)

    await insert_chunks(
        pg_session,
        document_id=document.id,
        company_id=company.id,
        document_type=document.document_type.value,
        year=2025,
        source="test",
        filename="f.pdf",
        chunks=chunks,
        embeddings=embeddings,
    )
    await pg_session.commit()

    query_embedding = await embedder.embed_query("Apple iPhone revenue")
    results = await dense_search(pg_session, query_embedding, top_k=2)

    assert len(results) == 2
    # The two Apple-revenue chunks should outrank the weather chunk.
    top_contents = {r.chunk.content for r in results}
    assert "weather" not in " ".join(top_contents).lower()


async def test_dense_search_respects_company_filter(pg_session):
    apple, apple_doc = await _make_document(pg_session, company_name="Apple")
    msft, msft_doc = await _make_document(pg_session, company_name="Microsoft")

    for company, document, text in [
        (apple, apple_doc, "Apple revenue grew sharply."),
        (msft, msft_doc, "Microsoft cloud revenue grew sharply."),
    ]:
        chunk = Chunk(chunk_index=0, content=text, page_number=1, section=None, token_count=4)
        embedding = await embedder.embed_documents([text])
        await insert_chunks(
            pg_session,
            document_id=document.id,
            company_id=company.id,
            document_type=document.document_type.value,
            year=2025,
            source="test",
            filename="f.pdf",
            chunks=[chunk],
            embeddings=embedding,
        )
    await pg_session.commit()

    query_embedding = await embedder.embed_query("revenue grew")
    results = await dense_search(
        pg_session,
        query_embedding,
        top_k=5,
        filters=RetrievalFilters(company_id=apple.id),
    )

    assert len(results) == 1
    assert results[0].chunk.company_id == apple.id
