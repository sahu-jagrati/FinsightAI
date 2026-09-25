import pytest

from app.agents.calculation_agent import run_calculation_agent
from app.agents.state import ExtractedMetric, QueryUnderstanding, ResearchState

pytestmark = pytest.mark.asyncio


def _metric(company, metric_name, value, year, unit="usd_billions") -> ExtractedMetric:
    return ExtractedMetric(
        company=company,
        metric_name=metric_name,
        value=value,
        unit=unit,
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


async def test_percent_annotations_do_not_pollute_dollar_metric_cagr():
    """Regression test: a real SEC table extraction yields both the dollar
    revenue figure AND its adjacent YoY-change percentage under the same
    metric_name ("revenue") — see extraction_agent's known limitation. A
    stray percent value must never be mistaken for a beginning/ending
    dollar amount in a CAGR calculation."""
    state = ResearchState(
        query="q",
        db=None,
        llm=None,
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(operations=["cagr"]),
        extracted_metrics=[
            _metric("Apple", "revenue", 100, 2022, unit="usd_billions"),
            _metric("Apple", "revenue", 150, 2025, unit="usd_billions"),
            _metric("Apple", "revenue", 6, 2025, unit="percent"),  # YoY-change annotation
        ],
    )

    await run_calculation_agent(state)

    assert len(state.calculations) == 1
    assert state.calculations[0].inputs["beginning_value"] == 100
    assert state.calculations[0].inputs["ending_value"] == 150


async def test_conflicting_same_year_values_are_not_guessed_between():
    """The old behavior picked the LARGEST same-year value on the theory
    that the company total beats its segments. That was a guess: it is what
    let unrelated values from other tables/contexts win just because their
    label was similar. Segment rows are no longer extracted as the metric
    (row labels must match exactly), so two different, uncorroborated values
    for one (metric, year) are now genuinely ambiguous — that year is left
    out rather than picked, and no calculation is produced from it."""
    state = ResearchState(
        query="q",
        db=None,
        llm=None,
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(operations=["cagr"]),
        extracted_metrics=[
            _metric("Apple", "revenue", 100, 2022, unit="usd"),
            _metric("Apple", "revenue", 300, 2022, unit="usd"),  # conflicts with the line above
            _metric("Apple", "revenue", 450, 2025, unit="usd"),
        ],
    )

    await run_calculation_agent(state)

    row = next(r for r in state.comparison_rows if r.metric == "revenue")
    assert row.values_by_year == {2025: 450}  # 2022 ambiguous -> excluded, not guessed
    assert row.calculation is None
    assert state.calculations == []


async def test_structured_table_row_outranks_conflicting_prose_mentions():
    """A statement's "Total net sales" row IS the metric; a prose sentence
    that merely mentions a different, similarly-labelled number for the same
    year must not compete with it."""
    table_total = ExtractedMetric(
        company="Apple", metric_name="revenue", value=416161, unit="usd_millions", period="2025",
        year=2025, source_page=25, source_document="f.pdf", confidence=0.9,
        label="Total net sales", extraction_path="table_row",
    )
    table_prior = ExtractedMetric(
        company="Apple", metric_name="revenue", value=391035, unit="usd_millions", period="2024",
        year=2024, source_page=25, source_document="f.pdf", confidence=0.9,
        label="Total net sales", extraction_path="table_row",
    )
    prose_other = _metric("Apple", "revenue", 209586, 2025, unit="usd_millions")
    state = ResearchState(
        query="q", db=None, llm=None, embedding_service=None, reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(metrics=["revenue"], years=[2024, 2025], operations=["growth"]),
        extracted_metrics=[prose_other, table_total, table_prior],
    )

    await run_calculation_agent(state)

    row = next(r for r in state.comparison_rows if r.metric == "revenue")
    assert row.values_by_year == {2024: 391035, 2025: 416161}
    assert row.unit == "usd_millions"


async def test_derives_net_margin_when_not_directly_stated():
    """Regression test: Section 13 requires margin support, and this is a
    named example query (Section 34 / real-data test plan Query 4:
    "compare net income margins"), but net/operating margin are virtually
    never stated as a labeled line item in a 10-K — they were never
    actually computed at all until this fix (query_understanding detected
    the "margin" operation, but calculation_agent had no code path that
    called `app/services/calculations.margin`)."""
    state = ResearchState(
        query="Compare the net income margins of Amazon and Walmart.",
        db=None,
        llm=None,
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(
            companies=["Amazon", "Walmart"], operations=["margin"], is_comparison=True
        ),
        extracted_metrics=[
            _metric("Amazon", "net_income", 30, 2025, unit="usd_billions"),
            _metric("Amazon", "revenue", 600, 2025, unit="usd_billions"),
            _metric("Walmart", "net_income", 15, 2025, unit="usd_billions"),
            _metric("Walmart", "revenue", 650, 2025, unit="usd_billions"),
        ],
    )

    await run_calculation_agent(state)

    margin_rows = {row.company: row for row in state.comparison_rows if row.metric == "net_margin"}
    assert set(margin_rows) == {"Amazon", "Walmart"}
    assert margin_rows["Amazon"].values_by_year[2025] == pytest.approx(5.0)  # 30/600 = 5%
    assert margin_rows["Walmart"].values_by_year[2025] == pytest.approx(15 / 650 * 100, abs=0.01)
    assert margin_rows["Amazon"].calculation.result == pytest.approx(0.05)


async def test_does_not_override_a_directly_extracted_margin():
    state = ResearchState(
        query="q",
        db=None,
        llm=None,
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(operations=["margin"]),
        extracted_metrics=[
            _metric("Apple", "net_margin", 27.0, 2025, unit="percent"),
            _metric("Apple", "net_income", 112, 2025, unit="usd_billions"),
            _metric("Apple", "revenue", 416, 2025, unit="usd_billions"),
        ],
    )

    await run_calculation_agent(state)

    margin_rows = [row for row in state.comparison_rows if row.metric == "net_margin"]
    assert len(margin_rows) == 1
    assert margin_rows[0].values_by_year == {2025: 27.0}


async def test_margin_metrics_only_use_percent_values():
    state = ResearchState(
        query="q",
        db=None,
        llm=None,
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(operations=["growth"]),
        extracted_metrics=[
            _metric("Apple", "net_margin", 25, 2022, unit="percent"),
            _metric("Apple", "net_margin", 30, 2023, unit="percent"),
            _metric("Apple", "net_margin", 99999, 2023, unit="usd"),  # not a margin value
        ],
    )

    await run_calculation_agent(state)

    row = next(r for r in state.comparison_rows if r.metric == "net_margin")
    assert row.values_by_year == {2022: 25, 2023: 30}


async def test_calculation_scoped_to_requested_years_when_table_has_extra_history():
    """Regression test for a real bug found end-to-end on a live Apple
    10-K: its "net sales by segment" table reports THREE fiscal years at
    once (2025, 2024, 2023 — completely normal 10-K formatting), and
    extraction correctly picked up all three. But the query only asked
    "the percentage change ... in fiscal year 2025 and fiscal year 2024"
    — without scoping, `average_growth` averaged the 2023->2024 AND
    2024->2025 rates together and reported a 2023->2025 span, silently
    answering a different question than the one asked. Two-plus of the
    query's named years being present must restrict the calculation (and
    the row) to exactly those years."""
    state = ResearchState(
        query="q",
        db=None,
        llm=None,
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(
            companies=["Apple"], metrics=["revenue"], years=[2024, 2025], operations=["growth"]
        ),
        extracted_metrics=[
            _metric("Apple", "revenue", 383285, 2023, unit="usd"),
            _metric("Apple", "revenue", 391035, 2024, unit="usd"),
            _metric("Apple", "revenue", 416161, 2025, unit="usd"),
        ],
    )

    await run_calculation_agent(state)

    row = next(r for r in state.comparison_rows if r.metric == "revenue")
    assert row.values_by_year == {2024: 391035, 2025: 416161}
    assert row.calculation is not None
    assert row.calculation.result == pytest.approx((416161 - 391035) / 391035)


async def test_calculation_uses_full_range_when_years_not_named():
    """The scoping fix above must not break the existing "no explicit
    years named" case (e.g. "Microsoft's 3-year revenue CAGR") — it should
    still span the full extracted range exactly as before."""
    state = ResearchState(
        query="q",
        db=None,
        llm=None,
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(operations=["cagr"]),  # no years named
        extracted_metrics=[
            _metric("Apple", "revenue", 383285, 2023, unit="usd"),
            _metric("Apple", "revenue", 391035, 2024, unit="usd"),
            _metric("Apple", "revenue", 416161, 2025, unit="usd"),
        ],
    )

    await run_calculation_agent(state)

    row = next(r for r in state.comparison_rows if r.metric == "revenue")
    assert row.values_by_year == {2023: 383285, 2024: 391035, 2025: 416161}
