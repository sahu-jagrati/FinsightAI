"""Calculation Agent (Section 13).

Groups the Financial Extraction Agent's dated data points by
(company, metric) and runs whichever deterministic calculation
`state.understanding.operations` asked for — CAGR, growth, average growth —
via `app/services/calculations.py`. The LLM never computes a number here;
this agent only decides *which* pure function to call and with what
arguments (Section 35).
"""

from collections import defaultdict

from app.agents.state import ComparisonRow, ResearchState
from app.services.calculations import CalculationError, average_growth, cagr


def _group_by_company_metric(state: ResearchState) -> dict[tuple[str, str], dict[int, float]]:
    groups: dict[tuple[str, str], dict[int, float]] = defaultdict(dict)
    for m in state.extracted_metrics:
        if m.year is None:
            continue
        # If the same (company, metric, year) appears more than once, keep
        # the highest-confidence extraction rather than silently overwriting.
        key = (m.company, m.metric_name)
        existing_year_value = groups[key].get(m.year)
        if existing_year_value is None:
            groups[key][m.year] = m.value
        # (Ties broken by first-seen; extraction order is retrieval-ranked.)
    return groups


async def run_calculation_agent(state: ResearchState) -> None:
    trace = state.new_trace("calculation_agent")
    trace.start(operations=state.understanding.operations)

    try:
        wants_cagr = "cagr" in state.understanding.operations
        wants_growth = "growth" in state.understanding.operations or wants_cagr

        groups = _group_by_company_metric(state)
        rows: list[ComparisonRow] = []

        for (company, metric), values_by_year in groups.items():
            if len(values_by_year) < 2:
                # Still worth surfacing as a row (single data point), just
                # with no calculation attached.
                rows.append(ComparisonRow(company=company, metric=metric, values_by_year=values_by_year))
                continue

            years_sorted = sorted(values_by_year)
            begin_year, end_year = years_sorted[0], years_sorted[-1]
            n_periods = end_year - begin_year

            calculation = None
            if wants_cagr and n_periods > 0:
                try:
                    calculation = cagr(
                        values_by_year[begin_year], values_by_year[end_year], n_periods
                    )
                except CalculationError:
                    calculation = None

            if calculation is None and wants_growth:
                try:
                    calculation = average_growth(values_by_year)
                except CalculationError:
                    calculation = None

            rows.append(
                ComparisonRow(
                    company=company, metric=metric, values_by_year=values_by_year, calculation=calculation
                )
            )
            if calculation is not None:
                state.calculations.append(calculation)

        state.comparison_rows = rows
        trace.complete(row_count=len(rows), calculation_count=len(state.calculations))
    except Exception as exc:  # noqa: BLE001
        trace.fail(str(exc))
        raise
