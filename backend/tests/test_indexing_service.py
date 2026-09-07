"""Postgres-only (see `pg_session` in conftest.py)."""

import pytest
from sqlalchemy import select

from app.models.company import Company
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import DocumentType
from app.services.indexing_service import index_document
from tests.fakes import FakeEmbeddingService

pytestmark = pytest.mark.asyncio


async def test_index_document_writes_chunks_with_denormalized_metadata(pg_session):
    company = Company(name="Apple")
    pg_session.add(company)
    await pg_session.flush()

    document = Document(
        company_id=company.id,
        filename="f.pdf",
        original_filename="apple_10k.pdf",
        document_type=DocumentType.ANNUAL_REPORT,
        reporting_period="FY2025",
        source="user upload",
        file_path="/tmp/f.pdf",
    )
    pg_session.add(document)
    await pg_session.flush()

    pages = [
        (1, "Overview\nApple had a strong year with record revenue."),
        (2, "Risk Factors\nSupply chain disruptions remain a key risk."),
    ]

    count = await index_document(pg_session, document, pages, FakeEmbeddingService())
    await pg_session.commit()

    assert count > 0

    result = await pg_session.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == document.id)
    )
    rows = result.scalars().all()
    assert len(rows) == count
    for row in rows:
        assert row.document_type == "annual_report"
        assert row.year == 2025
        assert row.company_id == company.id
        assert row.embedding is not None
        assert row.chunk_metadata["filename"] == "apple_10k.pdf"


async def test_index_document_with_no_pages_writes_nothing(pg_session):
    company = Company(name="Empty Co")
    pg_session.add(company)
    await pg_session.flush()
    document = Document(
        company_id=company.id,
        filename="f.pdf",
        original_filename="f.pdf",
        document_type=DocumentType.OTHER,
        file_path="/tmp/f.pdf",
    )
    pg_session.add(document)
    await pg_session.flush()

    count = await index_document(pg_session, document, [], FakeEmbeddingService())
    assert count == 0
