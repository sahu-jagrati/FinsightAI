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
