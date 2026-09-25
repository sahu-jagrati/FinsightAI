"""Data-quality audit regressions for the Calculation Agent: a percentage is
only ever computed when every required year is validated, in one unit, from
one resolved value — otherwise the row says "Insufficient data"."""

import pytest

from app.agents.calculation_agent import run_calculation_agent
from app.agents.state import ExtractedMetric, QueryUnderstanding, ResearchState

pytestmark = pytest.mark.asyncio


def _m(metric, value, year, unit="usd_millions", *, validated=True, path="table_row", label=None,
       company="Apple", chunk=None, confidence=0.9):
    return ExtractedMetric(
        company=company,
        metric_name=metric,
        value=value,
        unit=unit,
        period=str(year),
        year=year,
        source_page=32,
        source_document="f.pdf",
        confidence=confidence,
        label=label,
        extraction_path=path,
        year_validated=validated,
        chunk_id=chunk,
    )


def _state(metrics, *, years=(), ops=("growth",), wanted=(), companies=("Apple",)):
    return ResearchState(
        query="q",
        db=None,
        llm=None,
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(
            companies=list(companies),
            metrics=list(wanted),
            years=list(years),
            operations=list(ops),
        ),
        extracted_metrics=metrics,
    )


def _row(state, metric):
    return next(r for r in state.comparison_rows if r.metric == metric)


# --- 7: calculation only when both required years are validated -------------


async def test_calculates_when_both_requested_years_are_validated():
    state = _state(
        [_m("revenue", 391035, 2024), _m("revenue", 416161, 2025)], years=(2024, 2025), wanted=["revenue"]
    )
    await run_calculation_agent(state)

    row = _row(state, "revenue")
    assert row.calculation.result == pytest.approx((416161 - 391035) / 391035)
    assert row.calculation.operation.value == "percentage_change"
    assert row.calculation.inputs["begin_year"] == 2024 and row.calculation.inputs["end_year"] == 2025
    assert row.insufficient_reason is None


async def test_no_calculation_when_a_requested_year_is_missing():
    """Total liabilities had 2025 but no 2024. Only 2025 (plus an unrequested
    2023) is available — it must NOT quietly compute 2023->2025, and it must
    not invent 2024."""
    state = _state(
        [_m("total_liabilities", 285508, 2025), _m("total_liabilities", 290000, 2023)],
        years=(2024, 2025),
        wanted=["total_liabilities"],
    )
    await run_calculation_agent(state)

    row = _row(state, "total_liabilities")
    assert row.calculation is None
    assert row.values_by_year == {2025: 285508}  # only what is validated, only requested years
    assert "2024" in row.insufficient_reason and row.insufficient_reason.startswith("Insufficient data")
    assert state.calculations == []


async def test_unvalidated_years_never_feed_a_calculation():
    """A year merely copied from the query (year_validated=False) is a
    guess — with only one validated year the growth is not computable."""
    state = _state(
        [_m("revenue", 391035, 2024, validated=False), _m("revenue", 416161, 2025)],
        years=(2024, 2025),
        wanted=["revenue"],
    )
    await run_calculation_agent(state)

    row = _row(state, "revenue")
    assert row.calculation is None
    assert row.values_by_year == {2025: 416161}


async def test_a_single_named_year_needs_the_prior_year_for_growth():
    state = _state([_m("revenue", 416161, 2025)], years=(2025,), wanted=["revenue"])
    await run_calculation_agent(state)
    row = _row(state, "revenue")
    assert row.calculation is None and "2024" in row.insufficient_reason


async def test_requested_metric_with_no_data_becomes_an_insufficient_row_not_silence():
    state = _state(
        [_m("revenue", 391035, 2024), _m("revenue", 416161, 2025)],
        years=(2024, 2025),
        wanted=["revenue", "total_liabilities"],
    )
    await run_calculation_agent(state)

    row = _row(state, "total_liabilities")
    assert row.values_by_year == {} and row.calculation is None
    assert row.insufficient_reason.startswith("Insufficient data")


# --- 1/6: pairing and contamination --------------------------------------------


async def test_only_requested_metrics_are_tabulated():
    """The query asked about revenue; net income/EPS/assets sitting in the same
    retrieved chunks are not part of the answer."""
    state = _state(
        [
            _m("revenue", 391035, 2024), _m("revenue", 416161, 2025),
            _m("net_income", 93736, 2024), _m("net_income", 112010, 2025),
            _m("eps", 6.08, 2024, "usd_per_share"), _m("eps", 7.46, 2025, "usd_per_share"),
        ],
        years=(2024, 2025),
        wanted=["revenue"],
    )
    await run_calculation_agent(state)
    assert [r.metric for r in state.comparison_rows] == ["revenue"]


async def test_conflicting_values_for_one_year_are_excluded_not_guessed():
    state = _state(
        [_m("revenue", 391035, 2024), _m("revenue", 999, 2025), _m("revenue", 416161, 2025)],
        years=(2024, 2025),
        wanted=["revenue"],
    )
    await run_calculation_agent(state)

    row = _row(state, "revenue")
    assert 2025 not in row.values_by_year  # ambiguous
    assert row.calculation is None


async def test_corroboration_across_chunks_resolves_a_conflict():
    state = _state(
        [
            _m("revenue", 391035, 2024),
            _m("revenue", 416161, 2025, chunk="a"),
            _m("revenue", 416161, 2025, chunk="b"),
            _m("revenue", 999, 2025, chunk="c"),
        ],
        years=(2024, 2025),
        wanted=["revenue"],
    )
    await run_calculation_agent(state)
    assert _row(state, "revenue").values_by_year == {2024: 391035, 2025: 416161}


async def test_diluted_eps_is_the_headline_when_basic_and_diluted_both_exist():
    state = _state(
        [
            _m("eps", 6.11, 2024, "usd_per_share", label="Basic earnings per share"),
            _m("eps", 6.08, 2024, "usd_per_share", label="Diluted earnings per share"),
            _m("eps", 7.49, 2025, "usd_per_share", label="Basic earnings per share"),
            _m("eps", 7.46, 2025, "usd_per_share", label="Diluted earnings per share"),
        ],
        years=(2024, 2025),
        wanted=["eps"],
    )
    await run_calculation_agent(state)

    row = _row(state, "eps")
    assert row.values_by_year == {2024: 6.08, 2025: 7.46}
    assert row.unit == "usd_per_share"
    assert row.calculation.result == pytest.approx((7.46 - 6.08) / 6.08)


async def test_a_consolidated_total_line_beats_a_same_named_segment_line():
    state = _state(
        [
            _m("revenue", 416161, 2025, label="Total net sales"),
            _m("revenue", 178353, 2025, label="Net sales"),
            _m("revenue", 391035, 2024, label="Total net sales"),
            _m("revenue", 167045, 2024, label="Net sales"),
        ],
        years=(2024, 2025),
        wanted=["revenue"],
    )
    await run_calculation_agent(state)
    assert _row(state, "revenue").values_by_year == {2024: 391035, 2025: 416161}


# --- 3: units are never mixed ----------------------------------------------------


async def test_values_in_different_units_are_never_combined_into_one_series():
    """2024 in millions and 2025 in billions must not be subtracted/divided —
    the series keeps one unit (the one covering most years)."""
    state = _state(
        [
            _m("revenue", 391035, 2024, "usd_millions"),
            _m("revenue", 416161, 2025, "usd_millions"),
            _m("revenue", 416.161, 2025, "usd_billions", path="prose"),
        ],
        years=(2024, 2025),
        wanted=["revenue"],
    )
    await run_calculation_agent(state)
    row = _row(state, "revenue")
    assert row.unit == "usd_millions"
    assert row.values_by_year == {2024: 391035, 2025: 416161}


async def test_margin_metrics_are_compared_in_percentage_points_not_growth_rates():
    state = _state(
        [_m("gross_margin", 46.2, 2024, "percent"), _m("gross_margin", 46.9, 2025, "percent")],
        years=(2024, 2025),
        wanted=["gross_margin"],
    )
    await run_calculation_agent(state)

    row = _row(state, "gross_margin")
    assert row.calculation.operation.value == "percentage_point_difference"
    assert row.calculation.result == pytest.approx(0.7)
    assert row.unit == "percent"


async def test_derived_margins_refuse_to_mix_units():
    state = _state(
        [
            _m("net_income", 112010, 2025, "usd_millions"),
            _m("revenue", 416.161, 2025, "usd_billions"),
        ],
        ops=("margin",),
    )
    await run_calculation_agent(state)
    assert [r for r in state.comparison_rows if r.metric == "net_margin"] == []
