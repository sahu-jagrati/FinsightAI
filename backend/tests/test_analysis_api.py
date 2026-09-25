"""Postgres-only (see `pg_session`/`client_pg` in conftest.py). Exercises
`/api/analyze`, `/api/query` (SSE), and `/api/analyses*` end to end.

The embedding/LLM/reranker factories are monkeypatched to fakes so this
never needs a downloaded model or a real API key — same reasoning as
`tests/fakes.py` elsewhere.
"""

import json

import pytest

import app.agents.supervisor as supervisor_module
from app.models.company import Company
from app.models.document import Document
from app.models.enums import DocumentType
from app.rag.ingestion.chunker import PageLike, chunk_document
from app.rag.retrieval.reranker import IdentityReranker
from app.rag.retrieval.vector_store import insert_chunks
from tests.fakes import FakeEmbeddingService

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _patch_ai_factories(monkeypatch):
    embedder = FakeEmbeddingService()
    monkeypatch.setattr(supervisor_module, "get_embedding_service", lambda: embedder)
    monkeypatch.setattr(supervisor_module, "get_reranker", lambda: IdentityReranker())

    from app.rag.llm.providers.mock import MockLLMProvider

    monkeypatch.setattr(supervisor_module, "get_llm_provider", lambda: MockLLMProvider())
    return embedder


async def _seed_apple(db, embedder):
    company = Company(name="Apple")
    db.add(company)
    await db.flush()
    document = Document(
        company_id=company.id,
        filename="f.pdf",
        original_filename="apple_annual_report.pdf",
        document_type=DocumentType.ANNUAL_REPORT,
        reporting_period="2025",
        file_path="/tmp/f.pdf",
    )
    db.add(document)
    await db.flush()

    text = "Apple's total revenue was $391 billion in fiscal 2025, up from $383 billion in fiscal 2024."
    chunks = chunk_document([PageLike(page_number=25, text=text)])
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
    await db.commit()


async def _seed_apple_uploaded_without_reporting_period(db, embedder):
    """Reproduces exactly what a real user hit: uploading a 10-K through
    the UI without filling in a `reporting_period`, so every chunk gets
    `year=None` (see `metadata_extractor.extract_year`). The financial
    text is a real 10-K's shape — one chunk stating BOTH fiscal years'
    net sales together, the way an actual comparative table reads."""
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

    # Shaped exactly like the real filing's own table (verified live): an
    # explicit "2025 Change 2024 Change 2023" header ahead of the data row
    # is what lets `extraction_agent`'s positional year-alignment split
    # $416,161 / $391,035 / $383,285 into distinct fiscal years instead of
    # mislabeling all three with the same one — see
    # `extraction_agent._find_year_sequences`.
    text = (
        "The following table shows net sales by reportable segment for 2025, 2024 and 2023 "
        "(dollars in millions): 2025 Change 2024 Change 2023 Total net sales $ 416,161 6 % "
        "$ 391,035 2 % $ 383,285. Americas net sales increased during 2025 compared to 2024 "
        "primarily driven by higher net sales of iPhone and Services."
    )
    chunks = chunk_document([PageLike(page_number=25, text=text)])
    embeddings = await embedder.embed_documents([c.content for c in chunks])
    await insert_chunks(
        db,
        document_id=document.id,
        company_id=company.id,
        document_type=document.document_type.value,
        year=None,  # no reporting_period was supplied at upload
        source="test",
        filename=document.original_filename,
        chunks=chunks,
        embeddings=embeddings,
    )
    await db.commit()


async def test_analyze_endpoint_finds_evidence_when_document_has_no_reporting_period(
    client_pg, pg_session, _patch_ai_factories
):
    """End-to-end regression test for the real bug report: a live-uploaded
    Apple 10-K PDF with no `reporting_period` set returned "insufficient
    evidence" for "What was Apple's total net sales in fiscal year 2025
    and fiscal year 2024?" — retrieval's hard `year IN (2025, 2024)`
    filter matched zero rows against chunks that all had `year=None`, even
    though the exact answer was indexed and searchable. See the
    permissive-year-filter fix in `vector_store.apply_filters`."""
    await _seed_apple_uploaded_without_reporting_period(pg_session, _patch_ai_factories)

    resp = await client_pg.post(
        "/api/analyze",
        json={
            "query": (
                "What was Apple's total net sales in fiscal year 2025 and fiscal year 2024? "
                "Calculate the percentage change and explain the main reasons for the change "
                "based only on the uploaded annual report."
            )
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["result"]["insufficient_evidence"] is False
    assert body["result"]["sources"], "expected at least one cited source"
    retrieval_run = next(r for r in body["agent_runs"] if r["agent_name"] == "retrieval_agent")
    assert retrieval_run["status"] == "completed"
    assert retrieval_run["output"]["evidence_count"] > 0


async def test_analyze_endpoint_computes_yoy_change_and_reasons_end_to_end(
    client_pg, pg_session, _patch_ai_factories
):
    """Full pipeline regression test: this exact query was retrieving
    evidence (confirmed by the previous fix) but the Calculation Agent was
    being skipped — "Calculate the percentage change" was classified as
    only a "summary" operation, never "growth" — so the final answer
    stated just the 2025 figure with no 2024 figure, no dollar change, and
    no reasons. Runs the FULL supervisor -> retrieval -> extraction ->
    calculation -> report pipeline against real Postgres/pgvector and
    checks every agent that should fire actually did, and that the
    persisted answer is the complete structured comparison."""
    await _seed_apple_uploaded_without_reporting_period(pg_session, _patch_ai_factories)

    resp = await client_pg.post(
        "/api/analyze",
        json={
            "query": (
                "What was Apple's total net sales in fiscal year 2025 and fiscal year 2024? "
                "Calculate the percentage change and explain the main reasons for the change "
                "based only on the uploaded annual report."
            )
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["result"]["insufficient_evidence"] is False

    agents_run = {r["agent_name"]: r for r in body["agent_runs"]}
    assert agents_run["retrieval_agent"]["status"] == "completed"
    assert agents_run["financial_extraction_agent"]["status"] == "completed"
    assert "calculation_agent" in agents_run, "Calculation Agent was skipped"
    assert agents_run["calculation_agent"]["status"] == "completed"
    assert agents_run["calculation_agent"]["output"]["calculation_count"] > 0
    assert "comparison_agent" not in agents_run  # single-company: correctly not applicable

    result = body["result"]
    assert "416,161" in result["executive_summary"] or any(
        "416,161" in f for f in result["key_findings"]
    )
    findings_text = " ".join(result["key_findings"])
    assert "391,035" in findings_text  # 2024 figure must be present, not just 2025
    assert "25,126" in findings_text  # dollar change
    assert any("%" in f for f in result["key_findings"])  # percentage change
    assert any("Reason:" in f for f in result["key_findings"])  # grounded explanation
    assert len(result["comparison_table"]) >= 1
    assert result["comparison_table"][0]["values_by_year"].get("2024") == 391035
    assert result["comparison_table"][0]["values_by_year"].get("2025") == 416161
    assert result["confidence"] > 0


async def test_analyze_endpoint_returns_persisted_analysis_with_trace(client_pg, pg_session, _patch_ai_factories):
    await _seed_apple(pg_session, _patch_ai_factories)

    resp = await client_pg.post("/api/analyze", json={"query": "What was Apple's revenue?"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    assert body["result"]["insufficient_evidence"] is False
    assert any(r["agent_name"] == "retrieval_agent" for r in body["agent_runs"])
    assert all(r["status"] == "completed" for r in body["agent_runs"])


async def test_analyze_endpoint_insufficient_evidence(client_pg):
    resp = await client_pg.post("/api/analyze", json={"query": "What is the meaning of life?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"]["insufficient_evidence"] is True


async def test_analyze_rejects_too_short_query(client_pg):
    resp = await client_pg.post("/api/analyze", json={"query": "hi"})
    assert resp.status_code == 422


async def test_query_endpoint_streams_agent_events(client_pg, pg_session, _patch_ai_factories):
    await _seed_apple(pg_session, _patch_ai_factories)

    events = []
    async with client_pg.stream(
        "POST", "/api/query", json={"query": "What was Apple's revenue?"}
    ) as resp:
        assert resp.status_code == 200
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: ") :]))

    assert events[0]["agent"] == "supervisor"
    assert events[0]["status"] == "running"
    assert events[-1]["event"] == "final"
    assert events[-1]["report"]["insufficient_evidence"] is False
    assert "analysis_id" in events[-1]


async def test_list_and_get_analyses(client_pg, pg_session, _patch_ai_factories):
    await _seed_apple(pg_session, _patch_ai_factories)
    create_resp = await client_pg.post("/api/analyze", json={"query": "What was Apple's revenue?"})
    analysis_id = create_resp.json()["id"]

    list_resp = await client_pg.get("/api/analyses")
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] >= 1

    get_resp = await client_pg.get(f"/api/analyses/{analysis_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == analysis_id

    missing_resp = await client_pg.get("/api/analyses/00000000-0000-0000-0000-000000000000")
    assert missing_resp.status_code == 404


async def test_analyze_persists_a_title_derived_from_the_query(
    client_pg, pg_session, _patch_ai_factories
):
    """Research History (Recent Research): every persisted analysis gets a
    stable, human-scannable title, generated once at persist time."""
    await _seed_apple(pg_session, _patch_ai_factories)

    resp = await client_pg.post("/api/analyze", json={"query": "What was Apple's revenue?"})

    assert resp.json()["title"] == "What was Apple's revenue?"


async def test_analyses_list_returns_lightweight_summaries(
    client_pg, pg_session, _patch_ai_factories
):
    """The Recent Research sidebar list must not need to ship the full
    result/agent_runs payload — verifies the lightweight shape."""
    await _seed_apple(pg_session, _patch_ai_factories)
    await client_pg.post("/api/analyze", json={"query": "What was Apple's revenue?"})

    list_resp = await client_pg.get("/api/analyses")
    item = list_resp.json()["items"][0]

    assert "title" in item
    assert "confidence" in item
    assert "result" not in item
    assert "agent_runs" not in item


async def test_analyses_search_filters_by_query_text(client_pg, pg_session, _patch_ai_factories):
    await _seed_apple(pg_session, _patch_ai_factories)
    await client_pg.post("/api/analyze", json={"query": "What was Apple's revenue?"})
    await client_pg.post("/api/analyze", json={"query": "What is the meaning of life?"})

    resp = await client_pg.get("/api/analyses", params={"search": "Apple"})
    body = resp.json()

    assert body["total"] >= 1
    assert all("apple" in item["title"].lower() or "apple" in item["query"].lower() for item in body["items"])


async def test_analyses_search_with_no_match_returns_empty(client_pg, pg_session, _patch_ai_factories):
    await _seed_apple(pg_session, _patch_ai_factories)
    await client_pg.post("/api/analyze", json={"query": "What was Apple's revenue?"})

    resp = await client_pg.get("/api/analyses", params={"search": "zzz_no_such_query_zzz"})

    assert resp.json()["items"] == []


async def test_delete_analysis_removes_it_and_its_agent_runs(
    client_pg, pg_session, _patch_ai_factories
):
    await _seed_apple(pg_session, _patch_ai_factories)
    create_resp = await client_pg.post("/api/analyze", json={"query": "What was Apple's revenue?"})
    analysis_id = create_resp.json()["id"]

    delete_resp = await client_pg.delete(f"/api/analyses/{analysis_id}")
    assert delete_resp.status_code == 204

    get_resp = await client_pg.get(f"/api/analyses/{analysis_id}")
    assert get_resp.status_code == 404


async def test_delete_missing_analysis_returns_404(client_pg):
    resp = await client_pg.delete("/api/analyses/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


async def test_loading_a_persisted_analysis_does_not_rerun_the_pipeline(
    client_pg, pg_session, _patch_ai_factories
):
    """The core Research History requirement: reopening a past query must
    be a pure DB read — it must never invoke the agent pipeline again.
    Deletes the underlying indexed chunk first: if `GET /analyses/{id}`
    somehow re-ran retrieval, it would now find no evidence and flip the
    persisted `insufficient_evidence=False` result to True."""
    await _seed_apple(pg_session, _patch_ai_factories)
    create_resp = await client_pg.post("/api/analyze", json={"query": "What was Apple's revenue?"})
    analysis_id = create_resp.json()["id"]
    original_result = create_resp.json()["result"]
    assert original_result["insufficient_evidence"] is False

    from app.models.document_chunk import DocumentChunk

    await pg_session.execute(DocumentChunk.__table__.delete())
    await pg_session.commit()

    get_resp = await client_pg.get(f"/api/analyses/{analysis_id}")

    assert get_resp.status_code == 200
    assert get_resp.json()["result"] == original_result
