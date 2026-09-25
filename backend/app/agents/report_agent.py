"""Report Generation Agent (Section 15) + hallucination prevention
(Section 16).

Combines evidence, extracted metrics, calculations, and comparison
insights into the final answer. Two things make this "source-grounded"
rather than a bare LLM call:

1.  If retrieval found nothing, the LLM is never even asked — the report
    is the fixed "insufficient evidence" response, verbatim per Section 16.
2.  The prompt hands the LLM ONLY the retrieved evidence text (never
    "answer from general knowledge"), and if the configured provider can't
    produce real content (the mock provider, or any provider returning
    empty content), the executive summary falls back to a template built
    deterministically from the comparison insights / calculations /
    evidence already computed — still fully grounded, just not
    LLM-phrased. The app never fabricates a number either way.
"""

import re

from app.agents.financial_keywords import METRIC_KEYWORDS, PERCENT_METRICS
from app.agents.metric_resolution import resolve_series
from app.agents.state import Citation, ComparisonRow, ExtractedMetric, ReportResult, ResearchState
from app.rag.llm.base import LLMMessage
from app.services.calculations import CalculationError, CalculationResult, Operation, difference

INSUFFICIENT_EVIDENCE_MESSAGE = (
    "I couldn't find sufficient evidence in the indexed documents to answer this reliably."
)
_MAX_CONTEXT_ITEMS = 6
# Wide enough to carry a real 10-K narrative paragraph past its opening
# numbers table — was 500, which cut off mid-sentence right before the
# "reasons for the change" text on a real evidence chunk (verified: the
# useful "iPhone net sales increased ... primarily due to ..." sentences
# started ~380 chars in on a real Apple 10-K chunk and ran well past 500).
_MAX_SNIPPET_CHARS = 1500

_SYSTEM_PROMPT = (
    "You are FinSight AI, a financial research analyst. Answer the user's question using "
    "ONLY the evidence provided below — never use outside knowledge and never invent a "
    "number that isn't in the evidence. Be concise (2-4 sentences). If the evidence doesn't "
    "actually answer the question, say so explicitly instead of guessing."
)


def _format_source(item) -> str:
    label = f"{item.document_filename or 'source'}"
    if item.page_number:
        label += f", p. {item.page_number}"
    if item.company:
        label = f"{item.company} — {label}"
    return label


def _build_context(state: ResearchState) -> str:
    lines = []
    for i, item in enumerate(state.evidence[:_MAX_CONTEXT_ITEMS], start=1):
        snippet = item.content[:_MAX_SNIPPET_CHARS]
        lines.append(f"[{i}] ({_format_source(item)}): {snippet}")
    return "\n\n".join(lines)


def _metric_label(metric: str) -> str:
    return "EPS" if metric == "eps" else metric.replace("_", " ")


def _format_number(value: float) -> str:
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"


_SCALE_WORDS = {"usd_billions": " billion", "usd_millions": " million", "usd_thousands": " thousand"}


def _format_extracted_value(value: float, unit: str) -> str:
    """Renders a value in the unit it was reported in — never silently
    dropping a "million"/"billion" scale (a bare "$416,161" would read as
    dollars, not millions of dollars)."""
    if unit == "percent":
        return f"{value:g}%"
    if unit == "usd_per_share":
        return f"${value:,.2f}"
    sign = "-" if value < 0 else ""
    return f"{sign}${_format_number(abs(value))}{_SCALE_WORDS.get(unit, '')}"


def _format_signed_change(value: float, unit: str) -> str:
    sign = "+" if value > 0 else "-" if value < 0 else ""
    return f"{sign}{_format_extracted_value(abs(value), unit)}"


_PERCENT_SHAPED_OPERATIONS = {
    Operation.CAGR,
    Operation.PERCENTAGE_CHANGE,
    Operation.YOY_GROWTH,
    Operation.AVERAGE_GROWTH,
    Operation.MARGIN,
}


def _format_calculation(c: CalculationResult) -> str:
    """Operation-aware: a percentage-point difference or a ratio is not a
    percentage and must not be rendered as one."""
    if c.operation in _PERCENT_SHAPED_OPERATIONS:
        return f"{c.result:+.1%}" if c.operation != Operation.MARGIN else f"{c.result:.1%}"
    if c.operation == Operation.PERCENTAGE_POINT_DIFFERENCE:
        return f"{c.result:+.1f} percentage points"
    if c.operation == Operation.RATIO:
        return f"{c.result:.2f}x"
    return _format_number(c.result)


def _best_matching_metric(state: ResearchState) -> ExtractedMetric | None:
    """The single validated extracted metric that answers a plain lookup
    like "What was Apple's revenue in 2025?" — the metric the query named,
    in the year it asked about (else the latest validated year). Goes
    through `resolve_series`, so it only ever returns a year backed by the
    source text, from the structured statement row when there is one, and
    never picks between conflicting values by guessing (an ambiguous year
    is simply not answered from extraction)."""
    if not state.understanding.metrics:
        return None
    wanted = set(state.understanding.metrics)
    candidates = [
        series
        for (company, metric), series in resolve_series(state.extracted_metrics).items()
        if metric in wanted
        and series.values_by_year
        and (not state.understanding.companies or company in state.understanding.companies)
    ]
    if not candidates:
        return None

    requested_years = set(state.understanding.years)
    best: tuple[tuple, ExtractedMetric] | None = None
    for series in candidates:
        for year, source in series.sources.items():
            key = (year in requested_years if requested_years else False, year, source.confidence)
            if best is None or key > best[0]:
                best = (key, source)
    return best[1] if best else None


def _find_structured_comparison_rows(state: ResearchState) -> list[ComparisonRow]:
    """Every validated, calculated multi-year `ComparisonRow` for a metric
    the query named — the rows that turn a bare single-number answer into a
    full "2025 vs. 2024 + dollar change + % change" structured answer (one
    entry per metric, so a query naming EPS *and* revenue covers both).
    The arithmetic was done by the Calculation Agent (Section 13), never the
    LLM; rows with `insufficient_reason` (missing/unvalidated years) carry no
    calculation and are therefore never summarized as if they did.

    Regression context: this previously never found anything because the
    Calculation Agent itself was being skipped — see the `growth` keyword
    fix in `query_understanding.py`. It's unrelated to `comparison_agent`,
    which only populates `state.comparison_insights` for multi-company
    queries."""
    if not state.understanding.metrics:
        return []
    wanted_metrics = set(state.understanding.metrics)
    rows = [
        row
        for row in state.comparison_rows
        if row.metric in wanted_metrics and row.calculation is not None and len(row.values_by_year) >= 2
    ]
    if state.understanding.companies:
        rows = [r for r in rows if r.company in state.understanding.companies] or rows
    return rows


_REASON_MARKERS = (
    "primarily due to",
    "primarily driven by",
    "driven by",
    "due to",
    "as a result of",
    "attributable to",
)
_MAX_REASON_SENTENCES = 3
# A genuine MD&A explanation sentence ("X increased ... primarily due to
# Y.") runs well under this; a run past it is almost always a numeric
# table with no internal punctuation (dollar figures/percents don't
# contain periods) that the naive `.!?` sentence splitter below failed to
# break up — found live: a whole "Operating expenses ... Research and
# development $34,550 ... Percentage of total net sales 8%..." table got
# swept into one "sentence" purely because it incidentally contained both
# a marker phrase and the substring "total net sales" from an unrelated
# column header, misattributing an R&D explanation to a revenue query.
_MAX_REASON_SENTENCE_CHARS = 280
# The metric keyword must appear near the START of the sentence — its
# grammatical subject — not just anywhere in it. Without this, "Services
# gross margin increased ... primarily due to higher Services net sales
# ..." matched a revenue query on the incidental phrase "Services net
# sales" even though the sentence is actually explaining a GROSS MARGIN
# change, not a net-sales change (found live, same query).
_SUBJECT_WINDOW_CHARS = 60


def _extract_reason_sentences(
    state: ResearchState, metric_keywords: list[str]
) -> list[tuple[str, object]]:
    """Pulls the "why" sentences straight out of the retrieved evidence —
    never an LLM summary, never invented: only sentences that OPEN with
    the requested metric AND contain an explanatory marker phrase
    ("primarily due to", "driven by", ...), which is exactly how a 10-K's
    MD&A narrates a change ("iPhone net sales increased ... primarily due
    to higher net sales of Pro models."). Generic across any
    company/metric — nothing here is Apple-specific."""
    results: list[tuple[str, object]] = []
    seen: set[str] = set()
    for item in state.evidence:
        for sentence in re.split(r"(?<=[.!?])\s+", item.content):
            cleaned = sentence.strip()
            if len(cleaned) < 15 or len(cleaned) > _MAX_REASON_SENTENCE_CHARS or cleaned in seen:
                continue
            lowered = cleaned.lower()
            if not any(marker in lowered for marker in _REASON_MARKERS):
                continue
            subject = lowered[:_SUBJECT_WINDOW_CHARS]
            if metric_keywords and not any(kw in subject for kw in metric_keywords):
                continue
            seen.add(cleaned)
            results.append((cleaned, item))
            if len(results) >= _MAX_REASON_SENTENCES:
                return results
    return results


def _structured_change_summary(
    state: ResearchState, row: ComparisonRow
) -> tuple[str, list[str]]:
    """Builds the full "2025 vs 2024" narrative + itemized findings from an
    already-computed `ComparisonRow` (Section 13's calculation) plus
    evidence-grounded reason sentences (Section 16 — every figure and
    every reason traces back to something the agents actually found, never
    phrased or computed by an LLM)."""
    years_sorted = sorted(row.values_by_year)
    begin_year, end_year = years_sorted[0], years_sorted[-1]
    begin_value, end_value = row.values_by_year[begin_year], row.values_by_year[end_year]
    metric_label = _metric_label(row.metric)
    is_percent_metric = row.metric in PERCENT_METRICS

    begin_str = _format_extracted_value(begin_value, row.unit)
    end_str = _format_extracted_value(end_value, row.unit)
    change_label = "Change" if is_percent_metric else "Percentage change"
    pct_str = _format_calculation(row.calculation) if row.calculation else "n/a"

    dollar_change = None
    if not is_percent_metric:
        try:
            dollar_change = difference(end_value, begin_value)
        except CalculationError:
            dollar_change = None

    direction = "up from" if end_value > begin_value else "down from" if end_value < begin_value else "unchanged from"
    change_clause = f"({pct_str})"
    if dollar_change is not None:
        change_str = _format_signed_change(dollar_change.result, row.unit)
        change_clause = f"a change of {change_str} ({pct_str})"

    reasons = _extract_reason_sentences(state, METRIC_KEYWORDS.get(row.metric, [row.metric]))

    verb = "were" if metric_label.endswith(("assets", "liabilities", "expenses")) else "was"
    summary = (
        f"{row.company}'s {metric_label} {verb} {end_str} in {end_year}, "
        f"{direction} {begin_str} in {begin_year} — {change_clause}."
    )
    if reasons:
        summary += " " + reasons[0][0]

    findings = [
        f"{end_year} {row.company} {metric_label}: {end_str}",
        f"{begin_year} {row.company} {metric_label}: {begin_str}",
    ]
    if dollar_change is not None:
        findings.append(f"Dollar change ({begin_year}→{end_year}): {change_str}")
    findings.append(f"{change_label} ({begin_year}→{end_year}): {pct_str}")
    for sentence, item in reasons:
        findings.append(f"Reason: {sentence} ({_format_source(item)})")

    return summary, findings


def _template_summary(state: ResearchState, structured_summary: str | None) -> str:
    """Deterministic, fully-grounded fallback used when the LLM has
    nothing real to say (e.g. the mock provider) — never fabricates."""
    if state.comparison_insights:
        return " ".join(state.comparison_insights)

    if structured_summary is not None:
        return structured_summary

    if state.calculations:
        c = state.calculations[0]
        return f"{c.operation.value.replace('_', ' ').upper()}: {_format_calculation(c)} ({c.formula})."

    # No calculation/comparison was requested — Section 12's structured
    # extraction already found the number (verified against real 10-K
    # filings), so state it directly instead of falling through to a raw
    # top-ranked evidence snippet, which may be a policy paragraph that
    # merely mentions the topic rather than the sentence with the figure.
    best_metric = _best_matching_metric(state)
    if best_metric is not None:
        metric_label = best_metric.metric_name.replace("_", " ")
        value_str = _format_extracted_value(best_metric.value, best_metric.unit)
        period = best_metric.year or best_metric.period
        source = f"{best_metric.source_document or 'the indexed document'}"
        if best_metric.source_page:
            source += f", p. {best_metric.source_page}"
        return f"{best_metric.company}'s {metric_label} in {period} was {value_str} ({source})."

    top = state.evidence[0]
    return f"Based on {_format_source(top)}: {top.content[:280].strip()}"


# Below this, evidence is treated as "found nothing usable" even though
# retrieval technically returned chunks — dense/sparse search always
# returns its *least-bad* match, there's no notion of "no result" the way
# an empty list is. Verified against a real, deliberately unanswerable
# question ("Apple's stock exchange rate vs. Japanese yen futures on
# Mars"): the top chunk was a real, correctly-cited passage from the 10-K
# that had nothing to do with the question, sigmoid-normalized cross-
# encoder score 0.002 — Section 16 requires the fixed insufficient-
# evidence response here, not a real citation to irrelevant text.
_MIN_CONFIDENCE_FOR_ANSWER = 0.1


def _compute_confidence(state: ResearchState) -> float:
    if not state.evidence:
        return 0.0
    avg_evidence_score = sum(e.score for e in state.evidence) / len(state.evidence)
    confidence = max(0.0, min(1.0, avg_evidence_score))

    wanted_calculation = bool(
        set(state.understanding.operations) & {"cagr", "growth", "margin", "ratio"}
    )
    if wanted_calculation and not state.calculations:
        confidence *= 0.5  # asked for a number we couldn't actually compute

    return round(confidence, 3)


async def run_report_agent(state: ResearchState) -> None:
    trace = state.new_trace("report_agent")
    trace.start(evidence_count=len(state.evidence))

    try:
        if not state.evidence:
            state.report = ReportResult(
                executive_summary=INSUFFICIENT_EVIDENCE_MESSAGE,
                key_findings=[],
                comparison_table=[],
                calculations=[],
                sources=[],
                citations=[],
                confidence=0.0,
                insufficient_evidence=True,
            )
            trace.complete(insufficient_evidence=True)
            return

        confidence = _compute_confidence(state)
        if confidence < _MIN_CONFIDENCE_FOR_ANSWER:
            state.report = ReportResult(
                executive_summary=INSUFFICIENT_EVIDENCE_MESSAGE,
                key_findings=[],
                comparison_table=[],
                calculations=[],
                sources=[],
                citations=[],
                confidence=confidence,
                insufficient_evidence=True,
            )
            trace.complete(insufficient_evidence=True, confidence=confidence, reason="low_relevance")
            return

        # Computed once, used by BOTH the LLM-fallback summary and the
        # structured `key_findings` list below — the itemized breakdown
        # (both years, dollar change, % change, evidence-grounded reasons)
        # is included regardless of whether a real LLM or the template
        # produced `executive_summary`, so "the final answer" is always
        # structured, not just prose when the LLM happens to be quiet.
        # Calculation cards show validated calculations only: whatever is
        # attached to a displayed comparison row (the same rows the table
        # and chart render), so the three can never disagree. Rows-less
        # states (nothing was tabulated) fall back to the raw list.
        report_calculations = (
            [r.calculation for r in state.comparison_rows if r.calculation is not None]
            if state.comparison_rows
            else state.calculations
        )
        structured_summary = structured_findings = None
        structured_rows = _find_structured_comparison_rows(state)
        if structured_rows:
            parts = [_structured_change_summary(state, row) for row in structured_rows]
            structured_summary = " ".join(summary for summary, _ in parts)
            structured_findings = [f for _, findings in parts for f in findings]

        context = _build_context(state)
        response = await state.llm.chat(
            [
                LLMMessage("system", _SYSTEM_PROMPT),
                LLMMessage(
                    "user", f"Question: {state.query}\n\nEvidence:\n{context}"
                ),
            ]
        )

        executive_summary = response.content.strip()
        used_fallback = not executive_summary or executive_summary.startswith("[mock LLM")
        if used_fallback:
            executive_summary = _template_summary(state, structured_summary)

        key_findings = list(state.comparison_insights)
        if not key_findings and structured_findings:
            key_findings = structured_findings
        elif not key_findings:
            for c in report_calculations[:5]:
                key_findings.append(
                    f"{c.operation.value.replace('_', ' ').title()}: {_format_calculation(c)}"
                )

        sources = []
        citations = []
        seen = set()
        for item in state.evidence:
            label = _format_source(item)
            if label not in seen:
                seen.add(label)
                sources.append(label)
                citations.append(
                    Citation(
                        label=label,
                        company=item.company,
                        document_id=item.document_id,
                        document_filename=item.document_filename,
                        page_number=item.page_number,
                    )
                )

        state.report = ReportResult(
            executive_summary=executive_summary,
            key_findings=key_findings,
            comparison_table=state.comparison_rows,
            calculations=report_calculations,
            sources=sources,
            citations=citations,
            confidence=confidence,
            insufficient_evidence=False,
        )
        trace.complete(
            used_llm_fallback=used_fallback,
            confidence=state.report.confidence,
            source_count=len(sources),
        )
    except Exception as exc:  # noqa: BLE001
        trace.fail(str(exc))
        raise
