"""Comparison Agent (Section 14).

Only runs when the query involves 2+ companies. Retrieval, unit-aligned
extraction, and per-company calculation already happened upstream
(Retrieval / Extraction / Calculation Agents) — this agent's job is purely
comparative: for each metric more than one company has a calculated result
for, work out who's ahead and phrase that as a finding.

Known limitation (documented, not silently papered over): row values come
from whatever unit each source document used (Section 8's ExtractedMetric
keeps a `unit` field per data point, but `ComparisonRow` — shared with the
single-company Calculation Agent path — collapses to bare numbers per
year). Cross-company comparisons are only numerically sound today when
both companies' source documents report the metric in the same unit,
which is the common case for same-currency same-magnitude filings but not
guaranteed. A future pass would carry `unit` through `ComparisonRow` and
convert before comparing.
"""

from collections import defaultdict

from app.agents.state import ResearchState


async def run_comparison_agent(state: ResearchState) -> None:
    trace = state.new_trace("comparison_agent")
    trace.start(company_count=len(state.understanding.companies))

    try:
        by_metric: dict[str, list] = defaultdict(list)
        for row in state.comparison_rows:
            if row.calculation is not None:
                by_metric[row.metric].append(row)

        insights: list[str] = []
        for metric, rows in by_metric.items():
            if len(rows) < 2:
                continue
            ranked = sorted(rows, key=lambda r: r.calculation.result, reverse=True)
            leader, runner_up = ranked[0], ranked[1]
            metric_label = metric.replace("_", " ")
            insights.append(
                f"{leader.company}'s {metric_label} "
                f"({leader.calculation.result:+.1%}) outpaced {runner_up.company}'s "
                f"({runner_up.calculation.result:+.1%}) over the period covered."
            )

        state.comparison_insights = insights
        trace.complete(insight_count=len(insights))
    except Exception as exc:  # noqa: BLE001
        trace.fail(str(exc))
        raise
