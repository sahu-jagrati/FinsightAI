import pytest

from app.agents.comparison_agent import run_comparison_agent
from app.agents.state import ComparisonRow, QueryUnderstanding, ResearchState
from app.services.calculations import cagr

pytestmark = pytest.mark.asyncio


def _row(company, metric, begin, end, years=(2022, 2025)) -> ComparisonRow:
    n = years[1] - years[0]
    return ComparisonRow(
        company=company,
        metric=metric,
        values_by_year={years[0]: begin, years[1]: end},
        calculation=cagr(begin, end, n),
    )


async def test_identifies_leader_between_two_companies():
    state = ResearchState(
        query="q",
        db=None,
        llm=None,
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(companies=["Apple", "Microsoft"], is_comparison=True),
        comparison_rows=[
            _row("Apple", "revenue", 100, 130),  # smaller CAGR
            _row("Microsoft", "revenue", 100, 180),  # bigger CAGR
        ],
    )

    await run_comparison_agent(state)

    assert len(state.comparison_insights) == 1
    assert "Microsoft" in state.comparison_insights[0]
    assert state.comparison_insights[0].index("Microsoft") < state.comparison_insights[0].index(
        "Apple"
    )


async def test_no_insight_for_single_company():
    state = ResearchState(
        query="q",
        db=None,
        llm=None,
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(companies=["Apple"], is_comparison=False),
        comparison_rows=[_row("Apple", "revenue", 100, 130)],
    )

    await run_comparison_agent(state)
    assert state.comparison_insights == []


async def test_rows_without_calculation_are_ignored():
    state = ResearchState(
        query="q",
        db=None,
        llm=None,
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(companies=["Apple", "Microsoft"], is_comparison=True),
        comparison_rows=[
            ComparisonRow(company="Apple", metric="revenue", values_by_year={2022: 100}),
            ComparisonRow(company="Microsoft", metric="revenue", values_by_year={2022: 200}),
        ],
    )

    await run_comparison_agent(state)
    assert state.comparison_insights == []
