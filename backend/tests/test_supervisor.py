"""End-to-end supervisor test (Postgres-only — see `pg_session` in
conftest.py). Seeds two companies with dated revenue chunks and asserts the
full pipeline (understanding -> retrieval -> extraction -> calculation ->
comparison -> report) produces a grounded, cited comparison.
"""

import pytest

from app.agents.supervisor import run_research
from app.models.company import Company
from app.models.document import Document
from app.models.enums import DocumentType
from app.rag.retrieval.reranker import IdentityReranker
from app.rag.retrieval.vector_store import insert_chunks
from app.rag.ingestion.chunker import chunk_document, PageLike
from tests.fakes import FakeEmbeddingService

pytestmark = pytest.mark.asyncio


async def _seed_company_revenue(db, name: str, begin: float, end: float, embedder):
    company = Company(name=name)
    db.add(company)
    await db.flush()

    document = Document(
        company_id=company.id,
        filename="f.pdf",
        original_filename=f"{name.lower()}_annual_report.pdf",
        document_type=DocumentType.ANNUAL_REPORT,
        reporting_period="2025",
        file_path="/tmp/f.pdf",
    )
    db.add(document)
    await db.flush()

    text = (
        f"{name}'s total revenue was ${end:.0f} billion in fiscal 2025, "
        f"compared to ${begin:.0f} billion in fiscal 2022."
    )
    chunks = chunk_document([PageLike(page_number=12, text=text)], chunk_size_words=100)
    embeddings = await embedder.embed_documents([c.content for c in chunks])
    await insert_chunks(
        db,
        document_id=document.id,
        company_id=company.id,
        document_type=document.document_type.value,
        year=2025,
        source="test",
        filename=document.original_filename,
        chunks=chunks,
        embeddings=embeddings,
    )
    return company


async def test_full_pipeline_produces_cited_cagr_comparison(pg_session, pg_sessionmaker):
    embedder = FakeEmbeddingService()
    await _seed_company_revenue(pg_session, "Apple", begin=100, end=150, embedder=embedder)
    await _seed_company_revenue(pg_session, "Microsoft", begin=100, end=200, embedder=embedder)
    await pg_session.commit()

    from app.rag.llm.providers.mock import MockLLMProvider

    state = await run_research(
        "Compare Apple's and Microsoft's revenue growth from 2022 to 2025 and calculate their CAGR.",
        pg_session,
        llm=MockLLMProvider(),
        embedding_service=embedder,
        reranker=IdentityReranker(),
        session_factory=pg_sessionmaker,
    )

    assert state.understanding.companies == ["Apple", "Microsoft"] or set(
        state.understanding.companies
    ) == {"Apple", "Microsoft"}
    assert state.report is not None
    assert state.report.insufficient_evidence is False
    assert len(state.report.calculations) == 2
    assert len(state.comparison_insights) == 1
    assert "Microsoft" in state.comparison_insights[0]  # higher CAGR
    assert any("annual_report.pdf" in s for s in state.report.sources)

    agent_names = [t.agent_name for t in state.trace]
    assert agent_names == [
        "supervisor",
        "retrieval_agent",
        "financial_extraction_agent",
        "calculation_agent",
        "comparison_agent",
        "report_agent",
    ]
    assert all(t.status == "completed" for t in state.trace)


async def test_pipeline_returns_insufficient_evidence_for_unindexed_topic(
    pg_session, pg_sessionmaker
):
    from app.rag.llm.providers.mock import MockLLMProvider

    embedder = FakeEmbeddingService()
    state = await run_research(
        "What are Tesla's biggest supply chain risks in the Amazon rainforest?",
        pg_session,
        llm=MockLLMProvider(),
        embedding_service=embedder,
        reranker=IdentityReranker(),
        session_factory=pg_sessionmaker,
    )

    assert state.report.insufficient_evidence is True
    assert state.report.confidence == 0.0


async def test_supervisor_skips_calculation_agent_when_not_requested(pg_session, pg_sessionmaker):
    embedder = FakeEmbeddingService()
    await _seed_company_revenue(pg_session, "Apple", begin=100, end=150, embedder=embedder)
    await pg_session.commit()

    from app.rag.llm.providers.mock import MockLLMProvider

    state = await run_research(
        "What did Apple say about its revenue?",
        pg_session,
        llm=MockLLMProvider(),
        embedding_service=embedder,
        reranker=IdentityReranker(),
        session_factory=pg_sessionmaker,
    )

    agent_names = {t.agent_name for t in state.trace}
    assert "calculation_agent" not in agent_names
    assert "comparison_agent" not in agent_names
    assert "retrieval_agent" in agent_names
