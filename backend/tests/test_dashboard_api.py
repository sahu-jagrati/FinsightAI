"""Postgres-only (see `pg_session`/`client_pg` in conftest.py)."""

import pytest

from app.models.company import Company
from app.models.document import Document
from app.models.enums import DocumentStatus, DocumentType

pytestmark = pytest.mark.asyncio


async def test_dashboard_stats_reflects_seeded_data(client_pg, pg_session):
    company = Company(name="Apple")
    pg_session.add(company)
    await pg_session.flush()
    document = Document(
        company_id=company.id,
        filename="f.pdf",
        original_filename="apple_10k.pdf",
        document_type=DocumentType.ANNUAL_REPORT,
        status=DocumentStatus.INDEXED,
        page_count=42,
        file_path="/tmp/f.pdf",
    )
    pg_session.add(document)
    await pg_session.commit()

    resp = await client_pg.get("/api/dashboard/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["documents_total"] == 1
    assert body["companies_total"] == 1
    assert body["indexed_pages_total"] == 42
    assert body["documents_by_status"]["indexed"] == 1
    assert body["recent_documents"][0]["original_filename"] == "apple_10k.pdf"
    assert "cache_hit_rate" in body


async def test_dashboard_stats_empty_system(client_pg):
    resp = await client_pg.get("/api/dashboard/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["documents_total"] == 0
    assert body["avg_query_latency_ms"] is None
