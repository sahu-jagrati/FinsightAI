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


async def test_eps_rejects_implausibly_large_value_from_adjacent_computation_table():
    """Regression test for a real bug: Apple's 10-K EPS note lists
    "Numerator: $112,010 ... Diluted earnings per share $7.46" close
    enough together that the net income figure ($112,010) was the nearest
    dollar value to the "earnings per share" keyword and got extracted as
    a $112,010 EPS — an obviously implausible per-share figure."""
    item = EvidenceItem(
        chunk_id=uuid.uuid4(),
        content=(
            "Numerator: $ 112,010 $ 93,736 $ 96,995 "
            "Diluted earnings per share $ 7.46 $ 6.08 $ 6.13"
        ),
        company="Apple",
        document_filename="aapl_10k.html",
        page_number=36,
        section=None,
        score=0.9,
    )
    state = _make_state([item], years=[2025])

    await run_extraction_agent(state)

    eps_values = [m.value for m in state.extracted_metrics if m.metric_name == "eps"]
    assert eps_values
    assert all(v < 1000 for v in eps_values)
    assert 7.46 in eps_values


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


async def test_flattened_sec_table_uses_year_header_not_query_year():
    """Regression test for a real bug found testing against Apple's actual
    10-K: a flattened HTML table renders as
    "<year header> ... Total net sales <value> <value> <value>" with no
    year adjacent to any individual value. Without the year-sequence
    fallback, all three values were mislabeled with the query's year
    instead of their own — which silently breaks CAGR (every value lands
    in the same year, so there's nothing to compute a growth rate between).
    """
    item = EvidenceItem(
        chunk_id=uuid.uuid4(),
        content=(
            "2025 2024 2023 "
            "Total net sales $ 416,161 6 % $ 391,035 2 % $ 383,285 "
            "Cost of sales: Products 194,116 185,233 189,282"
        ),
        company="Apple",
        document_filename="aapl_10k.html",
        page_number=1,
        section=None,
        score=0.9,
    )
    # Query year_hint is 2025 — the bug made every value below claim 2025.
    state = _make_state([item], years=[2025])

    await run_extraction_agent(state)

    # Filtered to the dollar-amount extractions specifically: the same
    # table also yields "6%"/"2%" YoY-change annotations tagged as
    # "revenue" too (a separate, documented limitation — see
    # calculation_agent._PERCENT_METRICS), which is a different concern
    # from whether *this* fix correctly years the dollar figures.
    revenue_by_year = {
        m.year: m.value
        for m in state.extracted_metrics
        if m.metric_name == "revenue" and m.unit != "percent"
    }
    assert revenue_by_year == {2025: 416161.0, 2024: 391035.0, 2023: 383285.0}
