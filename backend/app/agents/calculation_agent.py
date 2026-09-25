"""Calculation Agent (Section 13).

Runs whichever deterministic calculation `state.understanding.operations`
asked for — CAGR, growth / percentage change, margin — over the
*validated* per-(company, metric) series from `metric_resolution`, via
`app/services/calculations.py`. The LLM never computes a number here
(Section 35).

A calculation is only produced when every year it needs is reliably
available:

* If the query names specific years, the row is scoped to exactly those
  years, and growth needs ALL of them (CAGR needs its two endpoints). A
  missing year yields a row with `insufficient_reason` and NO calculation —
  it never quietly falls back to a different span (e.g. 2023->2025 for a
  2024->2025 question).
* If no years are named ("3-year CAGR"), the full validated range is used.
* Percent-valued metrics (margins) are compared in percentage POINTS, not
  as a growth rate of a percentage.
"""

from app.agents.financial_keywords import PER_SHARE_METRICS, PERCENT_METRICS
from app.agents.metric_resolution import ResolvedSeries, resolve_series
from app.agents.state import ComparisonRow, ResearchState
from app.services.calculations import (
    CalculationError,
    CalculationResult,
    average_growth,
    cagr,
    margin,
    percentage_change,
    percentage_point_difference,
)

# Section 13 requires margin support, but net/operating margin are
# virtually never stated as a labeled line item in a 10-K the way revenue
# or net income are — they have to be *derived* from the two metrics that
# ARE always reported. (Gross margin is the exception — companies do
# sometimes disclose it directly, which is why it isn't listed here: a
# directly-extracted value already satisfies the query and takes priority
# over deriving one — see the guard in `_derive_margin_rows`.)
_DERIVED_MARGIN_METRICS: dict[str, tuple[str, str]] = {
    "net_margin": ("net_income", "revenue"),
    "operating_margin": ("operating_income", "revenue"),
}


def _default_unit(metric: str) -> str:
    if metric in PERCENT_METRICS:
        return "percent"
    return "usd_per_share" if metric in PER_SHARE_METRICS else "usd"


def _annotate(calc: CalculationResult, begin_year: int, end_year: int, unit: str) -> CalculationResult:
    """Attaches the period and unit the calculation covers so the UI can
    label "6.4% (2024→2025)" without guessing."""
    calc.inputs = {**calc.inputs, "begin_year": begin_year, "end_year": end_year, "unit": unit}
    return calc


def _derive_margin_rows(
    series_by_key: dict[tuple[str, str], ResolvedSeries],
) -> tuple[list[ComparisonRow], list[CalculationResult]]:
    """Computes net/operating margin = numerator / denominator (Section 13
    — always in Python, never the LLM) for every company that has both
    halves, in the SAME unit, for at least one shared year. Skips any
    (company, margin) the document already stated directly."""
    rows: list[ComparisonRow] = []
    calculations: list[CalculationResult] = []
    companies = {company for company, _metric in series_by_key}

    for margin_name, (numerator_metric, denominator_metric) in _DERIVED_MARGIN_METRICS.items():
        for company in companies:
            if (company, margin_name) in series_by_key:
                continue  # already directly extracted from the document
            numerator = series_by_key.get((company, numerator_metric))
            denominator = series_by_key.get((company, denominator_metric))
            if not numerator or not denominator or numerator.unit != denominator.unit:
                continue

            shared_years = sorted(set(numerator.values_by_year) & set(denominator.values_by_year))
            values_by_year: dict[int, float] = {}
            latest_calculation = None
            for year in shared_years:
                try:
                    result = margin(
                        numerator.values_by_year[year],
                        denominator.values_by_year[year],
                        label=margin_name.replace("_", " "),
                    )
                except CalculationError:
                    continue
                # Stored as percentage *points* (25.0, not 0.25) to match
                # how a directly-extracted percent metric is represented in
                # `values_by_year`; `latest_calculation.result` stays the
                # raw ratio the Comparison Agent's `:.1%` formatting expects.
                values_by_year[year] = round(result.result * 100, 2)
                latest_calculation = _annotate(result, year, year, "percent")

            if values_by_year:
                rows.append(
                    ComparisonRow(
                        company=company,
                        metric=margin_name,
                        values_by_year=values_by_year,
                        calculation=latest_calculation,
                        unit="percent",
                    )
                )
                if latest_calculation is not None:
                    calculations.append(latest_calculation)

    return rows, calculations


def _required_years(
    requested: set[int], wants_cagr: bool, wants_growth: bool
) -> set[int] | None:
    """The years a growth/CAGR calculation cannot be computed without, or
    None when the query didn't name any (use the validated range)."""
    if not requested or not wants_growth:
        return None
    if wants_cagr:
        return {min(requested), max(requested)}
    if len(requested) == 1:
        year = next(iter(requested))
        return {year - 1, year}  # "growth in 2025" = 2025 vs. the year before
    return set(requested)


def _calculate(
    series: ResolvedSeries,
    display_years: dict[int, float],
    *,
    wants_cagr: bool,
    wants_growth: bool,
) -> tuple[CalculationResult | None, str | None]:
    """(calculation, insufficient_reason). `display_years` is already
    scoped to the years the calculation may use."""
    years = sorted(display_years)
    begin_year, end_year = years[0], years[-1]
    begin, end = display_years[begin_year], display_years[end_year]

    try:
        if series.metric in PERCENT_METRICS:
            calc = percentage_point_difference(end, begin)
            return _annotate(calc, begin_year, end_year, "percentage_points"), None
        if wants_cagr and end_year > begin_year:
            return _annotate(cagr(begin, end, end_year - begin_year), begin_year, end_year, series.unit), None
        if wants_growth:
            if len(years) == 2 and end_year - begin_year == 1:
                calc = percentage_change(begin, end)
            else:
                calc = average_growth(display_years)
            return _annotate(calc, begin_year, end_year, series.unit), None
    except CalculationError as exc:
        return None, exc.message
    return None, None


async def run_calculation_agent(state: ResearchState) -> None:
    trace = state.new_trace("calculation_agent")
    trace.start(operations=state.understanding.operations)

    try:
        wants_cagr = "cagr" in state.understanding.operations
        wants_growth = "growth" in state.understanding.operations or wants_cagr
        wants_margin = "margin" in state.understanding.operations
        requested_years = set(state.understanding.years)
        requested_metrics = set(state.understanding.metrics)
        required = _required_years(requested_years, wants_cagr, wants_growth)

        series_by_key = resolve_series(state.extracted_metrics)
        rows: list[ComparisonRow] = []
        insufficient = 0
        ambiguous = sum(len(s.ambiguous_years) for s in series_by_key.values())

        for (company, metric), series in series_by_key.items():
            if requested_metrics and metric not in requested_metrics:
                continue  # not asked about (kept in `series_by_key` for margin derivation)
            if not series.values_by_year:
                continue

            values = dict(series.values_by_year)
            if len(requested_years) >= 2:
                values = {y: v for y, v in values.items() if y in requested_years}
            elif required:  # one named year + growth: that year vs. the year before
                values = {y: v for y, v in values.items() if y in required}

            calculation = None
            reason = None
            if wants_growth:
                missing = sorted((required or set()) - set(series.values_by_year))
                if missing:
                    reason = f"Insufficient data: no validated {metric.replace('_', ' ')} for {', '.join(map(str, missing))}"
                elif len(values) < 2:
                    reason = "Insufficient data: only one validated year available"
                else:
                    calculation, reason = _calculate(
                        series, values, wants_cagr=wants_cagr, wants_growth=wants_growth
                    )
                    if reason is not None:
                        reason = f"Insufficient data: {reason}"

            if reason is not None:
                insufficient += 1
            rows.append(
                ComparisonRow(
                    company=company,
                    metric=metric,
                    values_by_year=values,
                    calculation=calculation,
                    unit=series.unit,
                    insufficient_reason=reason,
                )
            )
            if calculation is not None:
                state.calculations.append(calculation)

        if wants_margin:
            margin_rows, margin_calculations = _derive_margin_rows(series_by_key)
            rows.extend(margin_rows)
            state.calculations.extend(margin_calculations)

        # A metric the query asked about but that has no validated data must
        # still be shown — as "Insufficient data" — rather than silently
        # vanishing from the table (which reads as "not asked"/"zero").
        if requested_metrics and (wants_growth or wants_margin):
            companies = state.understanding.companies or sorted(
                {c for c in (i.company for i in state.evidence) if c}
            )
            covered = {(r.company, r.metric) for r in rows}
            for company in companies:
                for metric in sorted(requested_metrics):
                    if (company, metric) in covered:
                        continue
                    insufficient += 1
                    rows.append(
                        ComparisonRow(
                            company=company,
                            metric=metric,
                            values_by_year={},
                            unit=_default_unit(metric),
                            insufficient_reason=(
                                f"Insufficient data: no validated {metric.replace('_', ' ')} "
                                "found in the retrieved evidence"
                            ),
                        )
                    )

        state.comparison_rows = rows
        trace.complete(
            row_count=len(rows),
            calculation_count=len(state.calculations),
            insufficient_count=insufficient,
            ambiguous_year_count=ambiguous,
        )
    except Exception as exc:  # noqa: BLE001
        trace.fail(str(exc))
        raise
