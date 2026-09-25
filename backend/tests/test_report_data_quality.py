"""Data-quality audit regressions for the Report Agent and the retrieval
path that feeds it."""

import uuid

import pytest

from app.agents.report_agent import run_report_agent
from app.agents.state import ComparisonRow, EvidenceItem, QueryUnderstanding, ResearchState
from app.rag.llm.providers.mock import MockLLMProvider
from app.rag.retrieval.hybrid_search import build_sparse_tsquery_text, query_topic_terms
from app.services.analysis_service import serialize_report
from app.services.calculations import percentage_change



def _evidence() -> EvidenceItem:
    return EvidenceItem(
        chunk_id=uuid.uuid4(),
        content="Balance sheet text.",
        company="Apple",
        document_filename="Apple_10-K-2025-As-Filed.pdf",
        page_number=32,
        section=None,
        score=0.9,
        document_id=uuid.uuid4(),
    )


def _row(metric, unit, begin, end, *, calc=True) -> ComparisonRow:
    return ComparisonRow(
        company="Apple",
        metric=metric,
        values_by_year={2024: begin, 2025: end},
        calculation=percentage_change(begin, end) if calc else None,
        unit=unit,
    )


def _state(rows, wanted) -> ResearchState:
    return ResearchState(
        query="q",
        db=None,
        llm=MockLLMProvider(),
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(
            companies=["Apple"], metrics=wanted, years=[2024, 2025], operations=["growth"]
        ),
        evidence=[_evidence()],
        comparison_rows=rows,
        calculations=[r.calculation for r in rows if r.calculation],
    )


# --- 3: unit handling in the answer -------------------------------------------


async def test_answer_states_the_reported_unit_scale():
    """"$416,161" alone reads as dollars; the filing reports millions."""
    state = _state([_row("revenue", "usd_millions", 391035, 416161)], ["revenue"])
    await run_report_agent(state)

    assert "$416,161 million" in state.report.executive_summary
    assert "$391,035 million" in state.report.executive_summary
    assert "+$25,126 million" in state.report.executive_summary


async def test_per_share_values_are_shown_as_dollars_per_share_without_a_scale():
    state = _state([_row("eps", "usd_per_share", 6.08, 7.46)], ["eps"])
    await run_report_agent(state)
    assert "$7.46" in state.report.executive_summary and "million" not in state.report.executive_summary
    assert "EPS" in state.report.executive_summary


async def test_a_decline_is_described_as_a_decline():
    state = _state([_row("total_liabilities", "usd_millions", 308030, 285508)], ["total_liabilities"])
    await run_report_agent(state)
    assert "down from" in state.report.executive_summary
    assert "total liabilities were" in state.report.executive_summary
    assert "-7.3%" in state.report.executive_summary


# --- 2: insufficient rows are not summarized as if computed ---------------------


async def test_insufficient_rows_are_not_summarized_and_have_no_calculation():
    insufficient = ComparisonRow(
        company="Apple",
        metric="total_liabilities",
        values_by_year={2025: 285508},
        calculation=None,
        unit="usd_millions",
        insufficient_reason="Insufficient data: no validated total liabilities for 2024",
    )
    state = _state([_row("eps", "usd_per_share", 6.08, 7.46), insufficient], ["eps", "total_liabilities"])
    await run_report_agent(state)

    assert "total liabilities" not in state.report.executive_summary.lower()
    assert not any("liabilities" in f.lower() for f in state.report.key_findings)
    serialized = serialize_report(state.report)
    liabilities = next(r for r in serialized["comparison_table"] if r["metric"] == "total_liabilities")
    assert liabilities["calculation"] is None
    assert liabilities["insufficient_reason"].startswith("Insufficient data")
    assert liabilities["unit"] == "usd_millions"


# --- 8: chart/table consistency at the API boundary -----------------------------


async def test_report_calculations_are_exactly_the_calculations_of_the_displayed_rows():
    """The calculation cards and the chart are built from the SAME rows as
    the Financial Comparison table — a stray calculation with no validated
    row behind it must not reach the API response."""
    rows = [_row("revenue", "usd_millions", 391035, 416161), _row("eps", "usd_per_share", 6.08, 7.46)]
    state = _state(rows, ["revenue", "eps"])
    stray = percentage_change(1, 292)  # e.g. the old EPS 6.11 -> 24 nonsense
    state.calculations.append(stray)

    await run_report_agent(state)

    assert state.report.calculations == [r.calculation for r in rows]
    assert stray not in state.report.calculations
    serialized = serialize_report(state.report)
    table_results = [r["calculation"]["result"] for r in serialized["comparison_table"]]
    card_results = [c["result"] for c in serialized["calculations"]]
    assert table_results == card_results


# --- retrieval: sparse search must not AND a whole natural-language question -----


def test_sparse_query_is_an_or_over_topical_terms_only():
    """`plainto_tsquery` ANDed every word of the question, so no real chunk
    matched and hybrid retrieval silently became dense-only — which is why a
    balance-sheet chunk was never surfaced for "total liabilities"."""
    question = (
        "What were Apple's total liabilities in fiscal year 2025 and fiscal year 2024? "
        "Calculate the percentage change and explain the main reasons."
    )
    terms = query_topic_terms(question)
    assert terms == ["apple", "total", "liabilities", "2025", "2024"]
    assert build_sparse_tsquery_text(question) == "apple | total | liabilities | 2025 | 2024"


def test_sparse_query_is_none_when_only_task_words_remain():
    assert build_sparse_tsquery_text("What was the calculation?") is None


def test_sparse_query_is_safe_for_the_tsquery_parser():
    text = build_sparse_tsquery_text("revenue'; DROP TABLE x; -- & | ! ( ) :*")
    assert all(ch.isalnum() or ch in " |" for ch in text)
