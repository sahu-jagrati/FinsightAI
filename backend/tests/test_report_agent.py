import uuid

import pytest

from app.agents.report_agent import INSUFFICIENT_EVIDENCE_MESSAGE, run_report_agent
from app.agents.state import ComparisonRow, EvidenceItem, ExtractedMetric, QueryUnderstanding, ResearchState
from app.rag.llm.providers.mock import MockLLMProvider
from app.services.calculations import average_growth, cagr

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


async def test_low_relevance_evidence_returns_insufficient_evidence_not_a_citation():
    """Regression test for a real Section 16 gap, found asking a
    deliberately unanswerable question against a real indexed 10-K:
    dense/sparse retrieval always returns its *least-bad* match — there's
    no "no result" the way an empty list is — so `state.evidence` was
    never empty, and the fixed insufficient-evidence message only fired
    when it was. The system didn't fabricate a number, but it DID cite a
    real, correctly-sourced passage that had nothing to do with the
    question, which is exactly what Section 16 says not to do."""
    state = ResearchState(
        query="What is the exchange rate between Apple's stock and yen futures on Mars?",
        db=None,
        llm=MockLLMProvider(),
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        evidence=[_evidence(content="Item 5. Market for Registrant's Common Equity...", score=0.002)],
    )

    await run_report_agent(state)

    assert state.report.insufficient_evidence is True
    assert state.report.executive_summary == INSUFFICIENT_EVIDENCE_MESSAGE
    assert state.report.sources == []
    assert state.report.citations == []


async def test_mock_llm_states_extracted_metric_for_plain_lookup():
    """Regression test: a real "what was X's revenue" query against a real
    10-K was extracting the right number (Section 12 worked) but the mock
    fallback ignored it and echoed an unrelated top-ranked evidence
    snippet instead. When extraction found the metric the query actually
    named, state it directly."""
    state = ResearchState(
        query="What was Apple's revenue in 2025?",
        db=None,
        llm=MockLLMProvider(),
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(metrics=["revenue"], years=[2025]),
        evidence=[_evidence(content="Unrelated policy paragraph that happens to rank first.")],
        extracted_metrics=[
            ExtractedMetric(
                company="Apple",
                metric_name="revenue",
                value=416161,
                unit="usd",
                period="2025",
                year=2025,
                source_page=35,
                source_document="aapl_10k.html",
                confidence=0.9,
            ),
            # A same-named YoY-change annotation must not be picked instead.
            ExtractedMetric(
                company="Apple",
                metric_name="revenue",
                value=6,
                unit="percent",
                period="2025",
                year=2025,
                source_page=35,
                source_document="aapl_10k.html",
                confidence=0.9,
            ),
        ],
    )

    await run_report_agent(state)

    assert "416,161" in state.report.executive_summary
    assert "aapl_10k.html" in state.report.executive_summary
    assert "policy paragraph" not in state.report.executive_summary


async def test_mock_llm_does_not_guess_between_conflicting_same_year_figures():
    """Replaces the old "pick the largest figure" behavior. Real 10-K text
    used to yield both "Total net sales" ($416,161M) and per-product lines
    ($209,586M) tagged as the same metric+year, and the report picked the
    biggest. Picking among uncorroborated conflicting values is a guess; the
    report must not state a number from an ambiguous year (it falls back to
    the cited evidence text instead)."""

    def _metric(value):
        return ExtractedMetric(
            company="Apple", metric_name="revenue", value=value, unit="usd", period="2025",
            year=2025, source_page=35, source_document="aapl_10k.html", confidence=0.9,
        )

    state = ResearchState(
        query="What was Apple's revenue in 2025?",
        db=None,
        llm=MockLLMProvider(),
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(metrics=["revenue"], years=[2025]),
        evidence=[_evidence()],
        extracted_metrics=[_metric(209586), _metric(416161), _metric(60508)],
    )

    await run_report_agent(state)
    assert "416,161" not in state.report.executive_summary
    assert "209,586" not in state.report.executive_summary


async def test_mock_llm_states_the_statement_table_row_over_segment_prose():
    table_row = ExtractedMetric(
        company="Apple", metric_name="revenue", value=416161, unit="usd_millions", period="2025",
        year=2025, source_page=35, source_document="aapl_10k.html", confidence=0.9,
        label="Total net sales", extraction_path="table_row",
    )
    segment_prose = ExtractedMetric(
        company="Apple", metric_name="revenue", value=209586, unit="usd", period="2025",
        year=2025, source_page=35, source_document="aapl_10k.html", confidence=0.9,
    )
    state = ResearchState(
        query="What was Apple's revenue in 2025?",
        db=None,
        llm=MockLLMProvider(),
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(metrics=["revenue"], years=[2025]),
        evidence=[_evidence()],
        extracted_metrics=[segment_prose, table_row],
    )

    await run_report_agent(state)
    assert "$416,161 million" in state.report.executive_summary  # unit scale preserved


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


async def test_structured_answer_includes_both_years_dollar_change_and_reasons():
    """End-to-end regression test for the real bug report: "What was
    Apple's total net sales in fiscal 2025 and fiscal 2024? Calculate the
    percentage change and explain the main reasons..." was returning only
    the 2025 figure — no 2024 figure, no dollar change, no reasons — even
    though the Calculation Agent had already computed the year-over-year
    change from real extracted data. Once `state.comparison_rows` has that
    computed row, the Report Agent must surface all of it: both years,
    the dollar change, the percentage change, AND a reason sentence pulled
    verbatim from evidence — never inventing the explanation."""
    calc = average_growth({2024: 391035, 2025: 416161})
    row = ComparisonRow(
        company="Apple", metric="revenue", values_by_year={2024: 391035, 2025: 416161}, calculation=calc
    )
    reason_evidence = _evidence(
        content=(
            "Total net sales $ 416,161 6 % $ 391,035 2 % $ 383,285. "
            "iPhone net sales increased during 2025 compared to 2024 primarily due to "
            "higher net sales of Pro models."
        ),
        score=0.9,
    )
    state = ResearchState(
        query="q",
        db=None,
        llm=MockLLMProvider(),
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(
            companies=["Apple"], metrics=["revenue"], years=[2024, 2025], operations=["growth"]
        ),
        evidence=[reason_evidence],
        comparison_rows=[row],
        calculations=[calc],
    )

    await run_report_agent(state)

    summary = state.report.executive_summary
    assert "416,161" in summary
    assert "391,035" in summary
    findings_text = " ".join(state.report.key_findings)
    assert "416,161" in findings_text
    assert "391,035" in findings_text
    assert "25,126" in findings_text  # dollar change: 416,161 - 391,035
    assert any("%" in f for f in state.report.key_findings)
    assert any("Reason:" in f and "Pro models" in f for f in state.report.key_findings)


async def test_reason_extraction_ignores_unrelated_explanatory_sentences():
    """The reason heuristic must require BOTH an explanatory marker phrase
    AND a mention of the requested metric — a "due to" sentence about an
    unrelated line item (here, gross margin) must not be surfaced as a
    reason for a revenue query."""
    calc = average_growth({2024: 391035, 2025: 416161})
    row = ComparisonRow(
        company="Apple", metric="revenue", values_by_year={2024: 391035, 2025: 416161}, calculation=calc
    )
    unrelated_evidence = _evidence(
        content=(
            "Total net sales $ 416,161 $ 391,035. "
            "Products gross margin increased during 2025 compared to 2024 primarily due to "
            "favorable costs and a different mix of products."
        ),
        score=0.9,
    )
    state = ResearchState(
        query="q",
        db=None,
        llm=MockLLMProvider(),
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(
            companies=["Apple"], metrics=["revenue"], years=[2024, 2025], operations=["growth"]
        ),
        evidence=[unrelated_evidence],
        comparison_rows=[row],
        calculations=[calc],
    )

    await run_report_agent(state)

    assert not any("Reason:" in f for f in state.report.key_findings)
    assert "gross margin" not in state.report.executive_summary.lower()
