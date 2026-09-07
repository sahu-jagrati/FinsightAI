import pytest

from app.agents.calculation_agent import run_calculation_agent
from app.agents.state import ExtractedMetric, QueryUnderstanding, ResearchState

pytestmark = pytest.mark.asyncio


def _metric(company, metric_name, value, year) -> ExtractedMetric:
    return ExtractedMetric(
        company=company,
        metric_name=metric_name,
        value=value,
        unit="usd_billions",
        period=str(year),
        year=year,
        source_page=1,
        source_document="f.pdf",
        confidence=0.9,
    )


async def test_computes_cagr_when_requested():
    state = ResearchState(
        query="q",
        db=None,
        llm=None,
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(operations=["cagr"]),
        extracted_metrics=[
            _metric("Apple", "revenue", 100, 2022),
            _metric("Apple", "revenue", 150, 2025),
        ],
    )

    await run_calculation_agent(state)

    assert len(state.calculations) == 1
    assert state.calculations[0].result == pytest.approx((150 / 100) ** (1 / 3) - 1, rel=1e-9)
    assert len(state.comparison_rows) == 1
    assert state.comparison_rows[0].company == "Apple"
    assert state.comparison_rows[0].metric == "revenue"


async def test_no_calculation_without_operation_requested():
    state = ResearchState(
        query="q",
        db=None,
        llm=None,
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(operations=[]),  # nothing requested
        extracted_metrics=[
            _metric("Apple", "revenue", 100, 2022),
            _metric("Apple", "revenue", 150, 2025),
        ],
    )

    await run_calculation_agent(state)

    assert state.calculations == []
    # still surfaces the raw data as a row, just with no calculation
    assert state.comparison_rows[0].calculation is None


async def test_single_data_point_produces_row_without_calculation():
    state = ResearchState(
        query="q",
        db=None,
        llm=None,
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(operations=["cagr"]),
        extracted_metrics=[_metric("Apple", "revenue", 100, 2022)],
    )

    await run_calculation_agent(state)

    assert state.calculations == []
    assert len(state.comparison_rows) == 1
    assert state.comparison_rows[0].calculation is None


async def test_multi_company_produces_separate_rows():
    state = ResearchState(
        query="q",
        db=None,
        llm=None,
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(operations=["cagr"]),
        extracted_metrics=[
            _metric("Apple", "revenue", 100, 2022),
            _metric("Apple", "revenue", 150, 2025),
            _metric("Microsoft", "revenue", 200, 2022),
            _metric("Microsoft", "revenue", 350, 2025),
        ],
    )

    await run_calculation_agent(state)

    companies = {row.company for row in state.comparison_rows}
    assert companies == {"Apple", "Microsoft"}
    assert len(state.calculations) == 2
