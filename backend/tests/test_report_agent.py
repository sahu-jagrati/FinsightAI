import uuid

import pytest

from app.agents.report_agent import INSUFFICIENT_EVIDENCE_MESSAGE, run_report_agent
from app.agents.state import EvidenceItem, QueryUnderstanding, ResearchState
from app.rag.llm.providers.mock import MockLLMProvider
from app.services.calculations import cagr

pytestmark = pytest.mark.asyncio


def _evidence(content="Apple revenue was $391B.", company="Apple", score=0.8) -> EvidenceItem:
    return EvidenceItem(
        chunk_id=uuid.uuid4(),
        content=content,
        company=company,
        document_filename="apple_10k.pdf",
        page_number=25,
        section="Revenue",
        score=score,
        document_id=uuid.uuid4(),
    )


async def test_no_evidence_returns_fixed_insufficient_evidence_message():
    state = ResearchState(
        query="q",
        db=None,
        llm=MockLLMProvider(),
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
    )

    await run_report_agent(state)

    assert state.report.insufficient_evidence is True
    assert state.report.executive_summary == INSUFFICIENT_EVIDENCE_MESSAGE
    assert state.report.confidence == 0.0
    assert state.report.sources == []


async def test_mock_llm_falls_back_to_grounded_template():
    state = ResearchState(
        query="What was Apple's revenue?",
        db=None,
        llm=MockLLMProvider(),
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        evidence=[_evidence()],
    )

    await run_report_agent(state)

    assert state.report.insufficient_evidence is False
    # never echoes the raw mock placeholder text to the user
    assert "[mock LLM" not in state.report.executive_summary
    assert "apple_10k.pdf" in state.report.sources[0]
    assert state.report.confidence > 0


async def test_calculations_surface_in_findings_when_no_comparison():
    calc = cagr(100, 150, 3)
    state = ResearchState(
        query="q",
        db=None,
        llm=MockLLMProvider(),
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        evidence=[_evidence()],
        calculations=[calc],
    )

    await run_report_agent(state)

    assert any("Cagr" in f or "CAGR" in f for f in state.report.key_findings)
    assert state.report.calculations == [calc]


async def test_comparison_insights_take_priority_in_findings():
    state = ResearchState(
        query="q",
        db=None,
        llm=MockLLMProvider(),
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        evidence=[_evidence()],
        comparison_insights=["Microsoft's growth outpaced Apple's."],
    )

    await run_report_agent(state)
    assert state.report.key_findings == ["Microsoft's growth outpaced Apple's."]


async def test_sources_are_deduplicated():
    same = _evidence()
    state = ResearchState(
        query="q",
        db=None,
        llm=MockLLMProvider(),
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        evidence=[same, same],
    )
    await run_report_agent(state)
    assert len(state.report.sources) == 1


async def test_confidence_penalized_when_calculation_was_requested_but_missing():
    state = ResearchState(
        query="q",
        db=None,
        llm=MockLLMProvider(),
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(operations=["cagr"]),
        evidence=[_evidence(score=0.9)],
        calculations=[],  # requested but nothing computed
    )
    await run_report_agent(state)

    baseline_state = ResearchState(
        query="q",
        db=None,
        llm=MockLLMProvider(),
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        evidence=[_evidence(score=0.9)],
    )
    await run_report_agent(baseline_state)

    assert state.report.confidence < baseline_state.report.confidence
