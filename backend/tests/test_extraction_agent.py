import uuid

import pytest

from app.agents.extraction_agent import run_extraction_agent
from app.agents.state import EvidenceItem, QueryUnderstanding, ResearchState

pytestmark = pytest.mark.asyncio


def _make_state(evidence: list[EvidenceItem], years: list[int] | None = None) -> ResearchState:
    return ResearchState(
        query="q",
        db=None,  # not used by the extraction agent
        llm=None,
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(years=years or []),
        evidence=evidence,
    )


async def test_extracts_revenue_with_magnitude_and_year():
    item = EvidenceItem(
        chunk_id=uuid.uuid4(),
        content="Apple's total revenue for fiscal 2025 was $391.04 billion, up from the prior year.",
        company="Apple",
        document_filename="apple_10k.pdf",
        page_number=25,
        section="Revenue",
        score=0.9,
    )
    state = _make_state([item])

    await run_extraction_agent(state)

    assert len(state.extracted_metrics) == 1
    m = state.extracted_metrics[0]
    assert m.metric_name == "revenue"
    assert m.value == pytest.approx(391.04)
    assert m.unit == "usd_billions"
    assert m.year == 2025
    assert m.source_page == 25
    assert m.confidence > 0


async def test_extracts_two_years_from_same_chunk_for_cagr():
    item = EvidenceItem(
        chunk_id=uuid.uuid4(),
        content=(
            "Revenue was $391 billion in fiscal 2025, compared to $383 billion in fiscal 2024 "
            "and $365 billion in fiscal 2023."
        ),
        company="Apple",
        document_filename="apple_10k.pdf",
        page_number=10,
        section=None,
        score=0.9,
    )
    state = _make_state([item])

    await run_extraction_agent(state)

    years_found = {m.year for m in state.extracted_metrics if m.metric_name == "revenue"}
    assert years_found == {2023, 2024, 2025}


async def test_no_extraction_without_company():
    item = EvidenceItem(
        chunk_id=uuid.uuid4(),
        content="Revenue was $100 million.",
        company=None,
        document_filename="f.pdf",
        page_number=1,
        section=None,
        score=0.5,
    )
    state = _make_state([item])
    await run_extraction_agent(state)
    assert state.extracted_metrics == []


async def test_falls_back_to_query_year_when_no_year_in_chunk():
    item = EvidenceItem(
        chunk_id=uuid.uuid4(),
        content="Net income was $99.8 billion for the year.",
        company="Apple",
        document_filename="f.pdf",
        page_number=5,
        section=None,
        score=0.8,
    )
    state = _make_state([item], years=[2025])
    await run_extraction_agent(state)

    assert state.extracted_metrics[0].year == 2025
