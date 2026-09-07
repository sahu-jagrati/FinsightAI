"""Financial Extraction Agent (Section 12).

Pulls structured (metric, value, unit, year) facts out of the Retrieval
Agent's evidence chunks. Regex/keyword-based rather than an LLM call —
Section 35 puts "extraction" on the LLM's side of the line in general, but
numeric extraction specifically benefits from being deterministic and
auditable: every extracted number keeps the source page and the exact
snippet it came from, and running it doesn't depend on `LLM_PROVIDER`
being anything but `mock`. A real LLM-based pass over ambiguous prose is a
reasonable future improvement layered on top of this, not a replacement.

Approach: find every "value with a currency/magnitude/percent signal" in
the chunk (never bare numbers — those are usually years or page refs, not
facts), then attribute each one to whichever metric keyword sits closest
to it in the text. This — rather than only looking in a window right after
a keyword — is what lets one sentence like "revenue was $391B in fiscal
2025, compared to $383B in fiscal 2024" yield two dated data points
instead of one; the Calculation Agent needs at least two to compute
anything (CAGR, YoY growth).
"""

import re

from app.agents.financial_keywords import METRIC_KEYWORDS
from app.agents.state import EvidenceItem, ExtractedMetric, ResearchState
from app.models.financial_metric import FinancialMetric

# A number, required to carry a currency/magnitude/percent signal so a
# bare year or page number is never mistaken for a financial value:
# "$391 billion", "391 billion", "12.5%" all qualify; a bare "2025" does not.
_VALUE_RE = re.compile(
    r"\$?\s?(?P<number>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s?(?P<magnitude>billion|bn|million|mm|thousand|k|%)?",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_YEAR_SEARCH_WINDOW = 60  # chars on either side of a value to find its year in
_MAX_KEYWORD_DISTANCE = 150  # chars a value may be from its nearest metric keyword
_MAGNITUDE_UNITS = {
    "billion": "usd_billions",
    "bn": "usd_billions",
    "million": "usd_millions",
    "mm": "usd_millions",
    "thousand": "usd_thousands",
    "k": "usd_thousands",
    "%": "percent",
}


def _find_year_near(text: str, start: int, end: int) -> int | None:
    """A value's year almost always sits immediately next to it — either
    "in fiscal 2025, revenue was $391B" (year before) or "$391B in fiscal
    2025" (year after). Forward is checked first and preferred: in text
    with several (value, year) pairs back to back, the *previous* pair's
    year can be raw-character-closer to the current value's START than its
    own trailing year is, which a plain nearest-by-distance-to-start
    search would get wrong. Only falls back to a backward search when
    nothing follows the value at all (e.g. it's the last figure in the
    sentence)."""
    forward_hi = min(len(text), end + _YEAR_SEARCH_WINDOW)
    forward_matches = list(_YEAR_RE.finditer(text, end, forward_hi))
    if forward_matches:
        nearest = min(forward_matches, key=lambda m: m.start() - end)
        return int(nearest.group())

    backward_lo = max(0, start - _YEAR_SEARCH_WINDOW)
    backward_matches = list(_YEAR_RE.finditer(text, backward_lo, start))
    if backward_matches:
        nearest = min(backward_matches, key=lambda m: start - m.start())
        return int(nearest.group())

    return None


def _keyword_hits(lowered: str) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for metric_name, keywords in METRIC_KEYWORDS.items():
        for keyword in keywords:
            start = 0
            while (idx := lowered.find(keyword, start)) != -1:
                hits.append((idx, metric_name))
                start = idx + len(keyword)
    return hits


def _nearest_metric(hits: list[tuple[int, str]], position: int) -> str | None:
    if not hits:
        return None
    idx, metric_name = min(hits, key=lambda h: abs(h[0] - position))
    return metric_name if abs(idx - position) <= _MAX_KEYWORD_DISTANCE else None


def _extract_from_evidence(item: EvidenceItem, year_hint: int | None) -> list[ExtractedMetric]:
    if not item.company:
        return []

    content = item.content
    hits = _keyword_hits(content.lower())
    if not hits:
        return []

    found: list[ExtractedMetric] = []
    for match in _VALUE_RE.finditer(content):
        raw_match = match.group(0)
        magnitude = (match.group("magnitude") or "").lower()
        if "$" not in raw_match and not magnitude:
            continue  # no currency/magnitude/percent signal -> probably a year, not a value

        metric_name = _nearest_metric(hits, match.start())
        if metric_name is None:
            continue

        try:
            value = float(match.group("number").replace(",", ""))
        except ValueError:
            continue

        unit = _MAGNITUDE_UNITS.get(magnitude, "usd")
        year = _find_year_near(content, match.start(), match.end()) or year_hint
        confidence = round(min(1.0, item.score * 0.8 + 0.2), 3)

        found.append(
            ExtractedMetric(
                company=item.company,
                metric_name=metric_name,
                value=value,
                unit=unit,
                period=str(year) if year else "unknown",
                year=year,
                source_page=item.page_number,
                source_document=item.document_filename,
                confidence=confidence,
                document_id=item.document_id,
                chunk_id=item.chunk_id,
                company_id=item.company_id,
            )
        )

    return found


async def run_extraction_agent(state: ResearchState) -> None:
    trace = state.new_trace("financial_extraction_agent")
    trace.start(evidence_count=len(state.evidence))

    try:
        year_hint = state.understanding.years[-1] if state.understanding.years else None
        extracted: list[ExtractedMetric] = []
        for item in state.evidence:
            extracted.extend(_extract_from_evidence(item, year_hint))

        state.extracted_metrics = extracted
        persisted = await _persist_metrics(state, extracted)
        trace.complete(extracted_count=len(extracted), persisted_count=persisted)
    except Exception as exc:  # noqa: BLE001
        trace.fail(str(exc))
        raise


async def _persist_metrics(state: ResearchState, extracted: list[ExtractedMetric]) -> int:
    """Writes to `financial_metrics` (Section 20) so extracted numbers
    outlive this one query — the Company Explorer's revenue/net income
    trends (Section 21) read from this table rather than re-running
    extraction on every page view. Best-effort: a persistence failure
    shouldn't fail the research query itself, since `state.extracted_metrics`
    already has what the Calculation/Report Agents need in memory.
    """
    if state.db is None:
        return 0

    rows = [
        FinancialMetric(
            company_id=m.company_id,
            document_id=m.document_id,
            chunk_id=m.chunk_id,
            metric_name=m.metric_name,
            value=m.value,
            unit=m.unit,
            period=m.period,
            year=m.year,
            source_page=m.source_page,
            confidence=m.confidence,
        )
        for m in extracted
        if m.company_id and m.document_id
    ]
    if not rows:
        return 0

    try:
        state.db.add_all(rows)
        await state.db.flush()
    except Exception:  # noqa: BLE001
        # A failed flush leaves the session's transaction in a "pending
        # rollback" state — every later operation on it (persisting the
        # Analysis + agent trace, most importantly) would raise
        # `PendingRollbackError` too unless it's rolled back here. This is
        # genuinely best-effort: swallow the persistence failure, but
        # recover the session so the rest of the request still works.
        await state.db.rollback()
        return 0
    return len(rows)
