"""Postgres-only (see `pg_session`/`client_pg` in conftest.py).

End-to-end data-quality regression: the real text of the uploaded Apple
10-K's income statement + balance sheet (page 32) is chunked, embedded,
stored in pgvector and pushed through the FULL agent pipeline via
`/api/analyze` — the path where EPS came out as 6.11 -> 24 (+292.8%) and
Total liabilities as "359,241" with no 2024.
"""

import pytest
from sqlalchemy import func, select

import app.agents.supervisor as supervisor_module
from app.models.company import Company
from app.models.document import Document
from app.models.enums import DocumentType
from app.models.financial_metric import FinancialMetric
from app.rag.ingestion.chunker import PageLike, chunk_document
from app.rag.retrieval.hybrid_search import sparse_search
from app.rag.retrieval.reranker import IdentityReranker
from app.rag.retrieval.vector_store import RetrievalFilters, insert_chunks
from tests.fakes import FakeEmbeddingService
from tests.test_extraction_data_quality import INCOME_STATEMENT_AND_BALANCE_SHEET

pytestmark = pytest.mark.asyncio

QUERY = (
    "Compare Apple's diluted EPS, total liabilities and total assets for fiscal year 2025 "
    "and fiscal year 2024 and calculate the percentage change."
)


@pytest.fixture(autouse=True)
def _patch_ai_factories(monkeypatch):
    embedder = FakeEmbeddingService()
    monkeypatch.setattr(supervisor_module, "get_embedding_service", lambda: embedder)
    monkeypatch.setattr(supervisor_module, "get_reranker", lambda: IdentityReranker())

    from app.rag.llm.providers.mock import MockLLMProvider

    monkeypatch.setattr(supervisor_module, "get_llm_provider", lambda: MockLLMProvider())
    return embedder


async def _seed_statements(db, embedder):
    company = Company(name="Apple")
    db.add(company)
    await db.flush()
    document = Document(
        company_id=company.id,
        filename="f.pdf",
        original_filename="Apple_10-K-2025-As-Filed.pdf",
        document_type=DocumentType.ANNUAL_REPORT,
        reporting_period=None,
        file_path="/tmp/f.pdf",
    )
    db.add(document)
    await db.flush()

    # Preceded by a caption chunk so the second chunk starts mid-table, like
    # the real document (whose "(In millions ...)" caption is cut off).
    pages = [PageLike(page_number=32, text=INCOME_STATEMENT_AND_BALANCE_SHEET)]
    chunks = chunk_document(pages)
    embeddings = await embedder.embed_documents([c.content for c in chunks])
    await insert_chunks(
        db,
        document_id=document.id,
        company_id=company.id,
        document_type=document.document_type.value,
        year=None,
        source="test",
        filename=document.original_filename,
        chunks=chunks,
        embeddings=embeddings,
    )
    await db.commit()
    return company, document


async def test_full_pipeline_pairs_every_metric_with_its_own_years_and_unit(
    client_pg, pg_session, _patch_ai_factories
):
    await _seed_statements(pg_session, _patch_ai_factories)

    resp = await client_pg.post("/api/analyze", json={"query": QUERY})

    assert resp.status_code == 200, resp.text
    result = resp.json()["result"]
    rows = {r["metric"]: r for r in result["comparison_table"]}
    assert set(rows) == {"eps", "total_liabilities", "total_assets"}

    assert rows["eps"]["values_by_year"] == {"2025": 7.46, "2024": 6.08}  # diluted, own years
    assert rows["eps"]["unit"] == "usd_per_share"
    assert rows["total_liabilities"]["values_by_year"] == {"2025": 285508, "2024": 308030}
    assert rows["total_liabilities"]["unit"] == "usd_millions"
    assert rows["total_assets"]["values_by_year"] == {"2025": 359241, "2024": 364980}
    assert 359241 not in rows["total_liabilities"]["values_by_year"].values()

    by_metric = {r["metric"]: r["calculation"] for r in result["comparison_table"]}
    assert by_metric["eps"]["result"] == pytest.approx((7.46 - 6.08) / 6.08)
    assert by_metric["total_liabilities"]["result"] == pytest.approx((285508 - 308030) / 308030)
    assert by_metric["total_assets"]["result"] == pytest.approx((359241 - 364980) / 364980)
    # the old nonsense EPS growth (6.11 -> 24 = +292.8%) can not reappear
    assert all(abs(c["result"]) < 1 for c in result["calculations"])

    # calculation cards are exactly the table rows' calculations (chart/table consistency)
    assert [c["result"] for c in result["calculations"]] == [
        r["calculation"]["result"] for r in result["comparison_table"] if r["calculation"]
    ]


async def test_persisted_metrics_are_validated_and_not_duplicated_by_repeat_queries(
    client_pg, pg_session, _patch_ai_factories
):
    await _seed_statements(pg_session, _patch_ai_factories)

    for _ in range(2):
        assert (await client_pg.post("/api/analyze", json={"query": QUERY})).status_code == 200

    rows = (await pg_session.execute(select(FinancialMetric))).scalars().all()
    assert rows, "expected extracted metrics to be persisted"
    assert all(r.year is not None for r in rows)  # unvalidated years are never stored
    keys = [(r.metric_name, r.year, r.value, r.chunk_id) for r in rows]
    assert len(keys) == len(set(keys))  # re-extraction replaced, not stacked


async def test_sparse_search_finds_the_balance_sheet_for_a_full_natural_language_question(
    pg_session, _patch_ai_factories
):
    """With `plainto_tsquery` this returned nothing (every word ANDed)."""
    company, _ = await _seed_statements(pg_session, _patch_ai_factories)

    results = await sparse_search(
        pg_session,
        "What were Apple's total liabilities in fiscal year 2025 and fiscal year 2024? "
        "Calculate the percentage change.",
        top_k=5,
        filters=RetrievalFilters(company_id=company.id),
    )

    assert results, "sparse search must contribute for a natural-language question"
    assert any("Total liabilities" in r.chunk.content for r in results)
    total = (await pg_session.execute(select(func.count()).select_from(FinancialMetric))).scalar_one()
    assert total == 0  # (sparse search alone persists nothing)
