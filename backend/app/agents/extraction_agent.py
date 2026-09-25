"""Financial Extraction Agent (Section 12).

Pulls structured (metric, value, unit, year) facts out of the Retrieval
Agent's evidence chunks. Regex/keyword-based rather than an LLM call —
numeric extraction benefits from being deterministic and auditable: every
extracted number keeps the source page and the exact row label / sentence
it came from, and running it doesn't depend on `LLM_PROVIDER`.

Two extraction paths, kept deliberately separate because real filings
break any single "nearest keyword to a number" heuristic (verified against
a live Apple 10-K, where that heuristic mislabeled EPS with "24 million
restricted stock units", "Total liabilities and shareholders' equity" as
total liabilities, and every EPS column with the same year):

1.  **Table rows** (`_extract_table_rows`). PDF/HTML tables flatten to one
    run of text: "Total net sales 416,161 391,035 383,285 Cost of sales:
    Products 194,116 ...". A row is a *label* followed by a *run of value
    cells*. The label must be EXACTLY a known metric label ("Total net
    sales", "Diluted earnings per share") — never a longer label that only
    contains a keyword ("Total cost of sales", "Total liabilities and
    shareholders' equity", "Percentage of total net sales"). Each value is
    mapped to a fiscal year by position against the nearest preceding
    year header ("2025 2024 2023", "September 27, 2025 September 28, 2024"),
    and ONLY when the number of value columns equals the number of header
    years — otherwise the year is left unvalidated instead of guessed.
    The unit's scale ("in millions") comes from the nearest preceding table
    caption, looking into the previous chunk when this chunk starts
    mid-table.
2.  **Prose** (`_extract_prose`). A value stated in a sentence ("revenue
    was $391 billion in fiscal 2025"). Sentences that are really flattened
    tables are skipped (the row path owns those), per-share metrics reject
    magnitude/percent values, and percent values are never attributed to a
    dollar metric (they're growth annotations, not the metric).

Every metric carries `year_validated` — True only when the year is backed
by the source text (aligned header column or an adjacent year mention);
the Calculation Agent never computes from an unvalidated year.
"""

import re
from dataclasses import dataclass

from sqlalchemy import delete, select

from app.agents.financial_keywords import (
    METRIC_KEYWORDS,
    METRIC_LABEL_EXTRAS,
    PER_SHARE_METRICS,
    PERCENT_METRICS,
)
from app.agents.state import EvidenceItem, ExtractedMetric, ResearchState
from app.models.document_chunk import DocumentChunk
from app.models.financial_metric import FinancialMetric

# --- shared patterns --------------------------------------------------------

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|november|december|"
    "jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
)
# What may sit BETWEEN two years for them to still be one table header:
# separators, "and"/"to", "Change" column labels, and "September 28,"-style
# period-end dates ("September 27, 2025 September 28, 2024").
_HEADER_GAP_RE = re.compile(
    r"^(?:[\s,;/&|\-–—%]|\band\b|\bto\b|\bthrough\b|\bchanges?\b|\bfiscal\b|\byears?\b|\bended\b|\bfy\b"
    rf"|(?:{_MONTHS})\.?\s*\d{{1,2}}(?:st|nd|rd|th)?)*$",
    re.IGNORECASE,
)
_MAX_HEADER_GAP_CHARS = 40
_HEADER_LOOKBACK_CHARS = 4000
_SCALE_LOOKBACK_CHARS = 6000
_CONTEXT_TAIL_CHARS = 2500

_SCALE_UNITS = {"millions": "usd_millions", "thousands": "usd_thousands", "billions": "usd_billions"}
_SCALE_PAREN_RE = re.compile(
    r"\([^()]*?\bin\s+(?P<scale>millions|thousands|billions)\b[^()]*\)", re.IGNORECASE
)
_SCALE_PLAIN_RE = re.compile(
    r"\b(?:dollars|amounts|usd|figures)\s+in\s+(?P<scale>millions|thousands|billions)\b"
    r"|\bin\s+(?P<scale2>millions|thousands|billions)\s*,?\s*except\b",
    re.IGNORECASE,
)

# A table value cell: "$ 416,161", "6 %", "(321)", "7.46", or a dash
# placeholder. Cells followed by a magnitude word belong to prose ("$391
# billion"), not to a table, and bare year-like numbers are headers.
_CELL_RE = re.compile(
    r"(?<![\w.,\-$])"
    r"(?P<open>\()?\s?(?P<dollar>\$)?\s?(?P<num>\d[\d,]*(?:\.\d+)?)(?P<close>\))?(?P<pct>\s?%)?"
    r"(?![\w\-]|[.,]\d)"
    r"(?!\s?(?:billion|bn|million|mm|thousand|k)\b)"
    r"|(?P<dash>[—–])",
    re.IGNORECASE,
)

# --- prose patterns ---------------------------------------------------------

_VALUE_RE = re.compile(
    r"\$?\s?(?P<number>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s?(?P<magnitude>billion|bn|million|mm|thousand|k|%)?",
    re.IGNORECASE,
)
_YEAR_SEARCH_WINDOW = 60  # chars on either side of a value to find its year in
_TABLE_LIKE_CELL_COUNT = 4  # a "sentence" with this many table cells is a flattened table
_MAGNITUDE_UNITS = {
    "billion": "usd_billions",
    "bn": "usd_billions",
    "million": "usd_millions",
    "mm": "usd_millions",
    "thousand": "usd_thousands",
    "k": "usd_thousands",
    "%": "percent",
}
# "Deferred revenue" / "cost of sales" are different line items than
# "revenue" / "sales" even though they contain the keyword.
_KEYWORD_PREFIX_DISQUALIFIERS = ("deferred ", "cost of ", "unearned ", "percentage of ")
_BALANCE_METRICS = {"total_assets", "total_liabilities"}

# Sanity bound, not a magnitude conversion: EPS is dollars per share and is
# never realistically above ~$1,000.
_METRIC_MAX_PLAUSIBLE_VALUE = {"eps": 1000.0}

_QUALIFIERS = {"basic", "diluted", "basic and diluted"}
_LABEL_PREFIXES = ("", "total ", "consolidated ", "total consolidated ")
_PER_SHARE_PREFIXES = ("basic ", "diluted ", "basic and diluted ")
_PERCENT_SUFFIXES = ("", " percentage", " percent", " %", " (%)")
_ABBREVIATION_TOKENS = {"inc.", "corp.", "co.", "ltd.", "no.", "u.s."}


def _build_allowed_labels() -> dict[str, str]:
    """exact normalized row label -> metric_name."""
    allowed: dict[str, str] = {}
    for metric, keywords in METRIC_KEYWORDS.items():
        bases = list(keywords) + METRIC_LABEL_EXTRAS.get(metric, [])
        prefixes = _LABEL_PREFIXES + (_PER_SHARE_PREFIXES if metric in PER_SHARE_METRICS else ())
        suffixes = _PERCENT_SUFFIXES if metric in PERCENT_METRICS else ("",)
        for base in bases:
            for prefix in prefixes:
                for suffix in suffixes:
                    allowed.setdefault(f"{prefix}{base}{suffix}", metric)
    return allowed


_ALLOWED_LABELS = _build_allowed_labels()


# --- year headers / scale ---------------------------------------------------


@dataclass
class _YearHeader:
    end_pos: int
    years: list[int]


def _find_year_headers(text: str) -> list[_YearHeader]:
    """Every run of 2+ years packed together with only header-ish text
    between them ("2025 2024 2023", "2025 Change 2024 Change 2023",
    "September 27, 2025 September 28, 2024"), as long as the years step
    strictly by one — so prose like "in 2025 and in 2019" isn't a header."""
    matches = list(_YEAR_RE.finditer(text))
    headers: list[_YearHeader] = []
    run: list[re.Match] = []

    def _flush() -> None:
        if len(run) < 2:
            return
        years = [int(m.group()) for m in run]
        steps = {b - a for a, b in zip(years, years[1:])}
        if steps == {-1} or steps == {1}:
            headers.append(_YearHeader(end_pos=run[-1].end(), years=years))

    for m in matches:
        if run:
            gap = text[run[-1].end() : m.start()]
            if len(gap) > _MAX_HEADER_GAP_CHARS or not _HEADER_GAP_RE.match(gap):
                _flush()
                run = []
        run.append(m)
    _flush()
    return headers


def _nearest_header(headers: list[_YearHeader], pos: int) -> _YearHeader | None:
    candidates = [h for h in headers if h.end_pos <= pos and pos - h.end_pos <= _HEADER_LOOKBACK_CHARS]
    return candidates[-1] if candidates else None


def _scale_before(text: str, pos: int) -> str | None:
    """The unit scale ("usd_millions", ...) declared by the nearest table
    caption before `pos` — "(dollars in millions)", "(In millions, except
    number of shares ...)". First scale named in a caption is the primary
    one ("In millions, except ... shares ... in thousands" -> millions)."""
    lo = max(0, pos - _SCALE_LOOKBACK_CHARS)
    window = text[lo:pos]
    best_end = -1
    best_scale: str | None = None
    for m in _SCALE_PAREN_RE.finditer(window):
        if m.end() > best_end:
            best_end, best_scale = m.end(), m.group("scale").lower()
    for m in _SCALE_PLAIN_RE.finditer(window):
        if m.end() > best_end:
            best_end, best_scale = m.end(), (m.group("scale") or m.group("scale2")).lower()
    return _SCALE_UNITS.get(best_scale) if best_scale else None


# --- table rows -------------------------------------------------------------


@dataclass
class _Cell:
    start: int
    end: int
    value: float | None  # None = dash placeholder
    is_percent: bool
    has_signal: bool  # $, thousands comma, decimal, %, or parentheses


def _parse_cell(m: re.Match) -> _Cell | None:
    if m.group("dash"):
        return _Cell(m.start(), m.end(), None, False, False)
    raw = m.group("num")
    has_signal = bool(
        m.group("dollar") or "," in raw or "." in raw or m.group("pct") or m.group("open")
    )
    try:
        value = float(raw.replace(",", ""))
    except ValueError:
        return None
    if not has_signal and 1900 <= value <= 2100:
        return None  # a bare year -> header text, not a value
    if m.group("open") and m.group("close"):
        value = -value
    return _Cell(m.start(), m.end(), value, bool(m.group("pct")), has_signal)


def _is_footnote_marker(cell: _Cell, run: list[_Cell]) -> bool:
    """A lone "(1)" at either edge of a value run is a footnote reference
    ("Services (1) 109,158 ...", "... $ 383,285 (1) Services net sales
    include ..."), not the value -1. Left in, it changes the run's column
    count and can shift every value one column against the year header."""
    if cell.value is None or cell.value >= 0 or cell.value != int(cell.value) or cell.value < -9:
        return False
    if cell.has_signal is False or cell.is_percent:
        return False
    others = [c for c in run if c is not cell and c.value is not None]
    return bool(others) and any(abs(c.value) >= 100 for c in others)  # type: ignore[arg-type]


def _trim_footnote_markers(run: list[_Cell], text: str) -> list[_Cell]:
    while len(run) > 1 and _is_footnote_marker(run[-1], run) and "$" not in text[run[-1].start : run[-1].end]:
        run = run[:-1]
    while len(run) > 1 and _is_footnote_marker(run[0], run) and "$" not in text[run[0].start : run[0].end]:
        run = run[1:]
    return run


def _cell_runs(text: str) -> list[list[_Cell]]:
    """Groups consecutive cells separated only by whitespace into runs."""
    runs: list[list[_Cell]] = []
    current: list[_Cell] = []
    for m in _CELL_RE.finditer(text):
        cell = _parse_cell(m)
        if cell is None:
            if current:
                runs.append(current)
                current = []
            continue
        if current and text[current[-1].end : cell.start].strip():
            runs.append(current)
            current = []
        current.append(cell)
    if current:
        runs.append(current)
    runs = [_trim_footnote_markers(r, text) for r in runs]
    return [r for r in runs if len(r) >= 2 or any(c.has_signal for c in r)]


def _split_label(gap: str) -> tuple[str, str | None, bool]:
    """From the text between the previous value run and this one, pulls
    out (row_label, parent_heading, hit_colon). The label is the trailing
    words back to the nearest number, colon, or sentence end; a colon
    boundary also yields the heading before it ("Earnings per share:")."""
    tokens = gap.split()
    label_tokens: list[str] = []
    hit_colon = False
    i = len(tokens) - 1
    while i >= 0 and len(label_tokens) < 8:
        tok = tokens[i]
        if any(ch.isdigit() for ch in tok.replace("(1)", "")) and not re.fullmatch(r"\(\d\)", tok):
            break
        if tok.endswith(":"):
            hit_colon = True
            break
        if tok == "|":
            break
        if tok.endswith(".") and tok.lower() not in _ABBREVIATION_TOKENS and label_tokens:
            break
        label_tokens.append(tok)
        i -= 1
    label_tokens.reverse()

    parent = None
    if hit_colon:
        parent_tokens = [tokens[i].rstrip(":")]
        j = i - 1
        while j >= 0 and len(parent_tokens) < 6:
            t = tokens[j]
            if any(ch.isdigit() for ch in t) or t.endswith(":") or t == "|":
                break
            parent_tokens.append(t)
            j -= 1
        parent = " ".join(reversed(parent_tokens))
    return " ".join(label_tokens), parent, hit_colon


def _normalize_label(label: str) -> str:
    label = re.sub(r"\(\d\)", "", label)
    label = label.strip(" :").lower()
    return re.sub(r"\s+", " ", label)


def _extract_table_rows(
    item: EvidenceItem, text: str, start_offset: int, year_hint: int | None
) -> tuple[list[ExtractedMetric], bool]:
    """Returns (metrics, needs_context) — `needs_context` is True when some
    row couldn't be dated or scaled from this chunk alone, meaning the
    previous chunk (where a cut-off header/caption lives) might help."""
    headers = _find_year_headers(text)
    found: list[ExtractedMetric] = []
    needs_context = False

    prev_end = 0
    last_parent: str | None = None
    for run in _cell_runs(text):
        run_start, run_end = run[0].start, run[-1].end
        gap = text[prev_end:run_start]
        prev_end = run_end

        label_raw, parent, _hit_colon = _split_label(gap)
        if parent:
            last_parent = parent
        normalized = _normalize_label(label_raw)
        if normalized in _QUALIFIERS and last_parent:
            normalized = f"{normalized} {_normalize_label(last_parent)}"
            label_raw = f"{label_raw} {last_parent}"
        elif normalized not in _QUALIFIERS:
            last_parent = None if not parent else last_parent

        metric_name = _ALLOWED_LABELS.get(normalized)
        if metric_name is None or run_start < start_offset:
            continue

        is_percent_metric = metric_name in PERCENT_METRICS
        values = [c for c in run if c.is_percent == is_percent_metric]
        if not values:
            continue  # e.g. a dollar "Total gross margin" row for the percent metric

        header = _nearest_header(headers, run_start)
        year_by_index: list[int] | None = None
        if header is not None and len(values) == len(header.years):
            year_by_index = header.years
        elif header is None:
            needs_context = True

        if metric_name in PER_SHARE_METRICS:
            unit = "usd_per_share"
        elif is_percent_metric:
            unit = "percent"
        else:
            unit = _scale_before(text, run_start) or "usd"
            if unit == "usd":
                needs_context = True

        for idx, cell in enumerate(values):
            if cell.value is None:
                continue
            max_plausible = _METRIC_MAX_PLAUSIBLE_VALUE.get(metric_name)
            if max_plausible is not None and abs(cell.value) > max_plausible:
                continue
            year = year_by_index[idx] if year_by_index else None
            found.append(
                ExtractedMetric(
                    company=item.company or "",
                    metric_name=metric_name,
                    value=cell.value,
                    unit=unit,
                    period=str(year) if year else "unknown",
                    year=year,
                    source_page=item.page_number,
                    source_document=item.document_filename,
                    confidence=round(min(1.0, item.score * 0.8 + 0.2), 3),
                    document_id=item.document_id,
                    chunk_id=item.chunk_id,
                    company_id=item.company_id,
                    label=label_raw.strip(" :"),
                    extraction_path="table_row",
                    year_validated=year is not None,
                )
            )
    return found, needs_context


# --- prose ------------------------------------------------------------------


def _find_year_near(text: str, start: int, end: int) -> int | None:
    """A prose value's year almost always sits immediately next to it —
    "in fiscal 2025, revenue was $391B" (year before) or "$391B in fiscal
    2025" (year after). Forward is checked first and preferred: in text with
    several (value, year) pairs back to back, the *previous* pair's year can
    be raw-character-closer to the current value's START than its own
    trailing year is."""
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


@dataclass
class _KeywordSpan:
    start: int
    end: int
    metric: str | None  # None = the keyword belongs to a different line item


def _keyword_spans(lowered: str) -> list[_KeywordSpan]:
    """Every metric keyword occurrence, longest phrase winning where phrases
    overlap ("net sales" beats the "sales" inside it). A keyword that is
    really part of a different line item ("deferred revenue", "cost of
    sales", "total liabilities AND shareholders' equity") is kept with
    metric None so it still claims the value that follows it."""
    spans: list[_KeywordSpan] = []
    for metric_name, keywords in METRIC_KEYWORDS.items():
        for keyword in keywords:
            start = 0
            while (idx := lowered.find(keyword, start)) != -1:
                start = idx + len(keyword)
                disqualified = lowered[max(0, idx - 12) : idx].endswith(
                    _KEYWORD_PREFIX_DISQUALIFIERS
                ) or (
                    metric_name in _BALANCE_METRICS
                    and lowered[idx + len(keyword) :].lstrip().startswith("and ")
                )
                end = idx + len(keyword)
                if lowered[end : end + 1] == "s" and not lowered[end + 1 : end + 2].isalpha():
                    end += 1  # "total revenue(s) of $713.2 billion"
                spans.append(_KeywordSpan(idx, end, None if disqualified else metric_name))
    spans.sort(key=lambda sp: (sp.start, -(sp.end - sp.start)))
    kept: list[_KeywordSpan] = []
    for sp in spans:
        if kept and sp.start < kept[-1].end:
            continue  # contained in / overlapping a longer phrase that started earlier
        kept.append(sp)
    return kept


# A prose number only counts as a metric's LEVEL when the sentence states it
# directly: "<metric> [for fiscal 2025] was|of|totaled $X". Anything else is a
# change ("revenue increased $50.1 billion"), an impact ("impacted operating
# income by $204 million"), a component ("Walmart U.S. had net sales of
# $483.0 billion"), or a forecast — none of which is the metric itself, and
# nearest-keyword attribution cannot tell them apart (verified on real
# Microsoft/Walmart/Amazon 10-Ks).
_LEVEL_LINK_RE = re.compile(
    r"^(?:\s+(?:for|in|during)\s+(?:the\s+)?(?:fiscal\s+)?(?:year\s+)?(?:19|20)\d{2})?"
    r"\s*(?:was|were|is|are|of|totaled|totalled|reached|stood\s+at|:)\s+"
    r"(?:approximately\s+|about\s+|roughly\s+)?$",
    re.IGNORECASE,
)
# "$391 billion in fiscal 2025, compared to $383 billion in fiscal 2024 and
# $365 billion ..." — further values of the SAME statement.
_CHAIN_LINK_RE = re.compile(
    r"^(?:\s+(?:in|for|during)\s+(?:fiscal\s+)?(?:year\s+)?(?:19|20)\d{2})?\s*,?\s*"
    r"(?:and|compared\s+(?:to|with)|versus|vs\.?)?\s*(?:approximately\s+|about\s+)?$",
    re.IGNORECASE,
)
# What may sit directly before the keyword for the sentence to be about the
# company-wide metric rather than a segment/product of it.
_COMPANY_LEVEL_MODIFIERS = {"total", "consolidated", "our", "annual", "the", "diluted", "basic"}


def _is_company_level_subject(before: str) -> bool:
    tokens = re.findall(r"[\w’'.-]+", before)
    if not tokens:
        return True  # the keyword opens the sentence
    last = tokens[-1].lower()
    return last in _COMPANY_LEVEL_MODIFIERS or last.endswith(("'s", "’s"))


def _owning_metric(
    sentence: str,
    spans: list[_KeywordSpan],
    match: re.Match,
    previous: tuple[str, int] | None,
) -> str | None:
    """The metric whose LEVEL this value states, or None. `previous` is the
    (metric, end) of the value accepted just before, for chained values."""
    before_spans = [sp for sp in spans if sp.end <= match.start()]
    if previous is not None:
        metric, prev_end = previous
        if _CHAIN_LINK_RE.match(sentence[prev_end : match.start()]):
            return metric
    if not before_spans:
        return None
    span = before_spans[-1]
    if span.metric is None or not _LEVEL_LINK_RE.match(sentence[span.end : match.start()]):
        return None
    if not _is_company_level_subject(sentence[: span.start]):
        return None
    return span.metric


def _sentences(content: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z$])", content) if s.strip()]


def _is_flattened_table(sentence: str) -> bool:
    return len(_cell_runs(sentence)) >= 1 and sum(len(r) for r in _cell_runs(sentence)) >= _TABLE_LIKE_CELL_COUNT


def _extract_prose(item: EvidenceItem, year_hint: int | None) -> list[ExtractedMetric]:
    found: list[ExtractedMetric] = []
    for sentence in _sentences(item.content):
        if _is_flattened_table(sentence):
            continue  # owned by the table-row path
        spans = _keyword_spans(sentence.lower())
        if not spans:
            continue
        previous: tuple[str, int] | None = None
        # Cells of a table row ("... $ 416,161 $ 391,035") belong to the
        # table-row path; reading them again as loose prose values would
        # duplicate them and stamp them with the query's year.
        table_spans = [(r[0].start, r[-1].end) for r in _cell_runs(sentence) if len(r) >= 2]
        for match in _VALUE_RE.finditer(sentence):
            if any(lo <= match.start() < hi for lo, hi in table_spans):
                continue
            raw_match = match.group(0)
            magnitude = (match.group("magnitude") or "").lower()
            if "$" not in raw_match and not magnitude:
                continue  # no currency/magnitude/percent signal -> probably a year, not a value

            metric_name = _owning_metric(sentence, spans, match, previous)
            if metric_name is None:
                continue

            unit = _MAGNITUDE_UNITS.get(magnitude, "usd")
            is_percent_value = unit == "percent"
            if metric_name in PER_SHARE_METRICS:
                if magnitude:  # "24 million restricted stock units" is not a per-share figure
                    continue
                unit = "usd_per_share"
            elif (metric_name in PERCENT_METRICS) != is_percent_value:
                continue  # a % next to a dollar metric is its growth annotation, not the metric

            try:
                value = float(match.group("number").replace(",", ""))
            except ValueError:
                continue
            max_plausible = _METRIC_MAX_PLAUSIBLE_VALUE.get(metric_name)
            if max_plausible is not None and value > max_plausible:
                continue

            previous = (metric_name, match.end())
            year = _find_year_near(sentence, match.start(), match.end())
            year_validated = year is not None
            if year is None and year_hint is not None:
                year = year_hint  # the query's year — a guess, never validated

            found.append(
                ExtractedMetric(
                    company=item.company or "",
                    metric_name=metric_name,
                    value=value,
                    unit=unit,
                    period=str(year) if year else "unknown",
                    year=year,
                    source_page=item.page_number,
                    source_document=item.document_filename,
                    confidence=round(min(1.0, item.score * 0.8 + 0.2), 3),
                    document_id=item.document_id,
                    chunk_id=item.chunk_id,
                    company_id=item.company_id,
                    extraction_path="prose",
                    year_validated=year_validated,
                )
            )
    return found


def _extract_from_evidence(
    item: EvidenceItem, year_hint: int | None, context: str = ""
) -> tuple[list[ExtractedMetric], bool]:
    if not item.company:
        return [], False
    text = f"{context} {item.content}" if context else item.content
    start_offset = len(context) + 1 if context else 0
    rows, needs_context = _extract_table_rows(item, text, start_offset, year_hint)
    return rows + _extract_prose(item, year_hint), needs_context


async def _preceding_chunk_tail(state: ResearchState, item: EvidenceItem) -> str:
    """The tail of the chunk right before this one in the same document —
    where a table caption/year header that the chunker cut off lives.
    Best-effort: any failure just means no extra context."""
    if state.db is None or item.chunk_id is None:
        return ""
    try:
        row = (
            await state.db.execute(
                select(DocumentChunk.document_id, DocumentChunk.chunk_index).where(
                    DocumentChunk.id == item.chunk_id
                )
            )
        ).first()
        if row is None or row.chunk_index <= 0:
            return ""
        previous = (
            await state.db.execute(
                select(DocumentChunk.content).where(
                    DocumentChunk.document_id == row.document_id,
                    DocumentChunk.chunk_index == row.chunk_index - 1,
                )
            )
        ).scalar_one_or_none()
    except Exception:  # noqa: BLE001
        return ""
    return (previous or "")[-_CONTEXT_TAIL_CHARS:]


async def run_extraction_agent(state: ResearchState) -> None:
    trace = state.new_trace("financial_extraction_agent")
    trace.start(evidence_count=len(state.evidence))

    try:
        year_hint = state.understanding.years[-1] if state.understanding.years else None
        extracted: list[ExtractedMetric] = []
        for item in state.evidence:
            metrics, needs_context = _extract_from_evidence(item, year_hint)
            if needs_context:
                context = await _preceding_chunk_tail(state, item)
                if context:
                    metrics, _ = _extract_from_evidence(item, year_hint, context=context)
            extracted.extend(metrics)

        state.extracted_metrics = extracted
        persisted = await _persist_metrics(state, extracted)
        trace.complete(
            extracted_count=len(extracted),
            validated_count=sum(1 for m in extracted if m.year is not None and m.year_validated),
            persisted_count=persisted,
        )
    except Exception as exc:  # noqa: BLE001
        trace.fail(str(exc))
        raise


async def _persist_metrics(state: ResearchState, extracted: list[ExtractedMetric]) -> int:
    """Writes to `financial_metrics` (Section 20) so extracted numbers
    outlive this one query — the Company Explorer's revenue/net income
    trends (Section 21) read from this table rather than re-running
    extraction on every page view.

    Only rows whose year is validated are stored (an unvalidated year would
    put a guessed point on someone's trend chart), and re-extracting a chunk
    REPLACES that chunk's previous rows instead of piling duplicates on top
    of them (and of any earlier, less accurate extraction).

    Best-effort: a persistence failure shouldn't fail the research query
    itself, since `state.extracted_metrics` already has what the
    Calculation/Report Agents need in memory."""
    if state.db is None:
        return 0

    chunk_ids = [item.chunk_id for item in state.evidence if item.chunk_id]
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
        if m.company_id and m.document_id and m.year is not None and m.year_validated
    ]
    if not rows and not chunk_ids:
        return 0

    try:
        if chunk_ids:
            await state.db.execute(delete(FinancialMetric).where(FinancialMetric.chunk_id.in_(chunk_ids)))
        if rows:
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
