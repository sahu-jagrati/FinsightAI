"""Turns raw `ExtractedMetric`s into validated per-(company, metric) year
series — the single place that decides which extracted numbers may be
shown or calculated from, shared by the Calculation and Report agents so
they can never disagree.

Rules (Section 16 — never present a guess as a fact):

* Only metrics whose year is validated (backed by the source text, not the
  query's year) participate.
* A percent value only ever belongs to a percent metric (margins); a
  percent next to a dollar metric is its growth annotation, not the metric.
* Structured table rows outrank prose mentions of the same metric — a
  statement's "Total net sales" row is the metric; a sentence about
  "iPhone net sales" is not.
* A series never mixes units: if a metric was extracted in more than one
  unit, the unit covering the most years (preferring an explicitly scaled
  one) is used and the rest are ignored.
* If the same (metric, year, unit) has several DIFFERENT values, the
  conflict is resolved only by evidence — the headline-variant label
  (diluted EPS), or the value corroborated by more than one chunk — and
  otherwise that year is left out as ambiguous rather than guessed.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from app.agents.financial_keywords import PERCENT_METRICS, PREFERRED_LABEL_HINT
from app.agents.state import ExtractedMetric


@dataclass
class ResolvedSeries:
    company: str
    metric: str
    unit: str
    values_by_year: dict[int, float] = field(default_factory=dict)
    ambiguous_years: set[int] = field(default_factory=set)
    sources: dict[int, ExtractedMetric] = field(default_factory=dict)
    """The extraction each year's value was taken from (page, document)."""


def is_eligible(m: ExtractedMetric) -> bool:
    if m.year is None or not m.year_validated:
        return False
    return (m.unit == "percent") == (m.metric_name in PERCENT_METRICS)


def _resolve_year(metric: str, candidates: list[ExtractedMetric]) -> ExtractedMetric | None:
    distinct = {m.value for m in candidates}
    if len(distinct) == 1:
        return max(candidates, key=lambda m: m.confidence)

    hint = PREFERRED_LABEL_HINT.get(metric)
    if hint:
        preferred = [m for m in candidates if m.label and hint in m.label.lower()]
        if preferred and len({m.value for m in preferred}) == 1:
            return max(preferred, key=lambda m: m.confidence)

    # A consolidated "Total ..." line beats a same-named segment/component
    # line ("Net sales" inside a segment note vs. the statement's "Total net
    # sales") — but only when the totals themselves agree.
    totals = [m for m in candidates if m.label and m.label.lower().startswith("total")]
    if totals and len(totals) < len(candidates) and len({m.value for m in totals}) == 1:
        return max(totals, key=lambda m: m.confidence)

    corroboration: Counter[float] = Counter()
    for value in distinct:
        corroboration[value] = len({m.chunk_id or id(m) for m in candidates if m.value == value})
    (top_value, top_count), *rest = corroboration.most_common()
    if top_count >= 2 and (not rest or top_count > rest[0][1]):
        return max((m for m in candidates if m.value == top_value), key=lambda m: m.confidence)
    return None


def resolve_series(metrics: list[ExtractedMetric]) -> dict[tuple[str, str], ResolvedSeries]:
    by_key: dict[tuple[str, str], list[ExtractedMetric]] = defaultdict(list)
    for m in metrics:
        if is_eligible(m):
            by_key[(m.company, m.metric_name)].append(m)

    resolved: dict[tuple[str, str], ResolvedSeries] = {}
    for (company, metric), candidates in by_key.items():
        table_rows = [m for m in candidates if m.extraction_path == "table_row"]
        pool = table_rows or candidates

        by_unit: dict[str, list[ExtractedMetric]] = defaultdict(list)
        for m in pool:
            by_unit[m.unit].append(m)
        unit = max(
            by_unit,
            key=lambda u: (len({m.year for m in by_unit[u]}), u != "usd", len(by_unit[u])),
        )

        series = ResolvedSeries(company=company, metric=metric, unit=unit)
        by_year: dict[int, list[ExtractedMetric]] = defaultdict(list)
        for m in by_unit[unit]:
            by_year[m.year].append(m)  # type: ignore[index]  # eligibility guarantees year
        for year, year_candidates in by_year.items():
            chosen = _resolve_year(metric, year_candidates)
            if chosen is None:
                series.ambiguous_years.add(year)
            else:
                series.values_by_year[year] = chosen.value
                series.sources[year] = chosen
        resolved[(company, metric)] = series
    return resolved
