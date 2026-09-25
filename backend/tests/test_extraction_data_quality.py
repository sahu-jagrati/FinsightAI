"""Data-quality audit regressions for the Financial Extraction Agent.

The text below is VERBATIM from the real uploaded Apple 10-K (pages 32 and
39) — the exact shapes that produced the suspicious UI values: EPS
6.11 -> 24 = +292.8%, "Total liabilities" of 359,241 with no 2024 value, and
figures from different tables mixed together because their labels looked
alike.
"""

import uuid

import pytest

from app.agents.extraction_agent import run_extraction_agent
from app.agents.state import EvidenceItem, QueryUnderstanding, ResearchState

pytestmark = pytest.mark.asyncio

INCOME_STATEMENT_AND_BALANCE_SHEET = (
    "shares, which are reflected in thousands, and per-share amounts) September 27, 2025 "
    "September 28, 2024 September 30, 2023 Net sales: Products $ 307,003 $ 294,866 $ 298,085 "
    "Services 109,158 96,169 85,200 Total net sales 416,161 391,035 383,285 Cost of sales: "
    "Products 194,116 185,233 189,282 Services 26,844 25,119 24,855 Total cost of sales 220,960 "
    "210,352 214,137 Gross margin 195,201 180,683 169,148 Operating expenses: Research and "
    "development 34,550 31,370 29,915 Selling, general and administrative 27,601 26,097 24,932 "
    "Total operating expenses 62,151 57,467 54,847 Operating income 133,050 123,216 114,301 "
    "Net income $ 112,010 $ 93,736 $ 96,995 Earnings per share: Basic $ 7.49 $ 6.11 $ 6.16 "
    "Diluted $ 7.46 $ 6.08 $ 6.13 Shares used in computing earnings per share: Basic 14,948,500 "
    "15,343,783 15,744,231 Diluted 15,004,697 15,408,095 15,812,547 See accompanying Notes to "
    "Consolidated Financial Statements. Apple Inc. | 2025 Form 10-K | 29 Apple Inc. (In millions, "
    "except number of shares, which are reflected in thousands, and par value) September 27, 2025 "
    "September 28, 2024 ASSETS: Current assets: Cash and cash equivalents $ 35,934 $ 29,943 "
    "Total current assets 147,957 152,987 Total assets $ 359,241 $ 364,980 LIABILITIES AND "
    "SHAREHOLDERS’ EQUITY: Current liabilities: Accounts payable $ 69,860 $ 68,960 Total current "
    "liabilities 165,631 176,392 Non-current liabilities: Term debt 78,328 85,750 Total liabilities "
    "285,508 308,030 Commitments and contingencies Shareholders’ equity: Common stock and additional "
    "paid-in capital, $0.00001 par value: 50,400,000 shares authorized 93,568 83,276 Total "
    "shareholders’ equity 73,733 56,950 Total liabilities and shareholders’ equity $ 359,241"
)

EPS_NOTE = (
    "Note 3 – Earnings Per Share The following table shows the computation of basic and diluted "
    "earnings per share for 2025, 2024 and 2023 (net income in millions and shares in thousands): "
    "2025 2024 2023 Numerator: Net income $ 112,010 $ 93,736 $ 96,995 Denominator: Weighted-average "
    "basic shares outstanding 14,948,500 15,343,783 15,744,231 Effect of dilutive share-based awards "
    "56,197 64,312 68,316 Weighted-average diluted shares 15,004,697 15,408,095 15,812,547 Basic "
    "earnings per share $ 7.49 $ 6.11 $ 6.16 Diluted earnings per share $ 7.46 $ 6.08 $ 6.13 "
    "Approximately 24 million restricted stock units (“RSUs”) were excluded from the computation "
    "of diluted earnings per share for 2023 because their effect would have been antidilutive."
)


def _item(content: str, page: int = 32) -> EvidenceItem:
    return EvidenceItem(
        chunk_id=uuid.uuid4(),
        content=content,
        company="Apple",
        document_filename="Apple_10-K-2025-As-Filed.pdf",
        page_number=page,
        section=None,
        score=0.9,
    )


def _state(items, years=None) -> ResearchState:
    return ResearchState(
        query="q",
        db=None,
        llm=None,
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(years=years or []),
        evidence=items,
    )


async def _extract(content: str, years=None, page: int = 32):
    state = _state([_item(content, page)], years=years)
    await run_extraction_agent(state)
    return state.extracted_metrics


def _by(metrics, metric_name, label_contains=None):
    return {
        m.year: m
        for m in metrics
        if m.metric_name == metric_name
        and (label_contains is None or label_contains in (m.label or "").lower())
    }


# --- 1 & 4: correct metric/year pairing, EPS ---------------------------------


async def test_eps_is_extracted_per_fiscal_year_from_its_own_row():
    """EPS previously came out as {2024: 6.11 (the basic variant), 2025: 24
    (from "24 million RSUs")}. Each fiscal-year column of the diluted and
    basic rows must land on ITS year, in dollars per share."""
    metrics = await _extract(EPS_NOTE, page=39)

    diluted = _by(metrics, "eps", "diluted")
    assert {y: m.value for y, m in diluted.items()} == {2025: 7.46, 2024: 6.08, 2023: 6.13}
    basic = _by(metrics, "eps", "basic")
    assert {y: m.value for y, m in basic.items()} == {2025: 7.49, 2024: 6.11, 2023: 6.16}
    assert all(
        m.unit == "usd_per_share" and m.year_validated for m in metrics if m.metric_name == "eps"
    )


async def test_eps_never_takes_a_share_count_or_magnitude_value():
    metrics = await _extract(EPS_NOTE, page=39)
    eps_values = [m.value for m in metrics if m.metric_name == "eps"]
    assert 24.0 not in eps_values  # "24 million restricted stock units"
    assert all(v < 100 for v in eps_values)  # never share counts (14,948,500) or net income


async def test_eps_on_the_income_statement_uses_the_basic_diluted_sub_rows():
    """"Earnings per share: Basic $ 7.49 ... Diluted $ 7.46 ..." — the row
    labels are just "Basic"/"Diluted"; the metric comes from the heading."""
    metrics = await _extract(INCOME_STATEMENT_AND_BALANCE_SHEET)
    diluted = {y: m.value for y, m in _by(metrics, "eps", "diluted").items()}
    assert diluted == {2025: 7.46, 2024: 6.08, 2023: 6.13}
    # "Shares used in computing earnings per share: Basic 14,948,500 ..."
    assert all(m.value < 100 for m in metrics if m.metric_name == "eps")


# --- 5: balance-sheet metrics -------------------------------------------------


async def test_total_liabilities_is_not_confused_with_total_assets_or_equity_line():
    """"Total liabilities and shareholders' equity $ 359,241" (the same
    figure as total ASSETS) was extracted as total liabilities with no 2024
    value; the real row is "Total liabilities 285,508 308,030"."""
    metrics = await _extract(INCOME_STATEMENT_AND_BALANCE_SHEET)

    liabilities = {y: m.value for y, m in _by(metrics, "total_liabilities").items()}
    assets = {y: m.value for y, m in _by(metrics, "total_assets").items()}
    assert liabilities == {2025: 285508.0, 2024: 308030.0}
    assert assets == {2025: 359241.0, 2024: 364980.0}
    assert 359241.0 not in liabilities.values()
    assert 0.00001 not in [m.value for m in metrics]  # "$0.00001 par value"


# --- 6: cross-table / cross-label contamination -------------------------------


async def test_similar_labels_from_other_rows_do_not_contaminate_revenue():
    """"Total cost of sales", segment rows ("Products", "Services") and the
    "Net sales:" section heading contain revenue keywords but are different
    line items."""
    metrics = await _extract(INCOME_STATEMENT_AND_BALANCE_SHEET)
    revenue = {y: m.value for y, m in _by(metrics, "revenue").items()}
    assert revenue == {2025: 416161.0, 2024: 391035.0, 2023: 383285.0}
    every_revenue_value = {m.value for m in metrics if m.metric_name == "revenue"}
    assert not every_revenue_value & {220960.0, 210352.0, 307003.0, 109158.0, 194116.0}


async def test_percentage_of_total_net_sales_rows_are_not_revenue():
    metrics = await _extract(
        "2025 2024 2023 Total operating expenses $ 62,151 $ 57,467 $ 54,847 "
        "Percentage of total net sales 15% 15% 14% Total net sales $ 416,161 $ 391,035 $ 383,285"
    )
    revenue = {y: m.value for y, m in _by(metrics, "revenue").items()}
    assert revenue == {2025: 416161.0, 2024: 391035.0, 2023: 383285.0}


async def test_deferred_revenue_and_percent_annotations_are_not_revenue():
    metrics = await _extract(
        "The Company had total deferred revenue of $13.7 billion and revenue grew 6% in 2025."
    )
    assert [m for m in metrics if m.metric_name == "revenue"] == []


# --- 1: year-header alignment --------------------------------------------------


async def test_year_headers_written_as_period_end_dates_align_columns():
    """"September 27, 2025 September 28, 2024 September 30, 2023" is the
    column header of a real statement — three dates, three columns — and
    the values sit ~900 characters after it (past the old fixed lookback)."""
    metrics = await _extract(INCOME_STATEMENT_AND_BALANCE_SHEET)
    net_income = {y: m.value for y, m in _by(metrics, "net_income").items()}
    assert net_income == {2025: 112010.0, 2024: 93736.0, 2023: 96995.0}
    opex = {y: m.value for y, m in _by(metrics, "total_expenses").items()}
    assert opex == {2025: 62151.0, 2024: 57467.0, 2023: 54847.0}


# --- 2: missing / unmappable years ---------------------------------------------


async def test_year_is_left_unvalidated_when_column_count_does_not_match_header():
    """A 3-year header over a 2-value row: guessing which two years the
    values belong to is exactly the mis-pairing bug — leave the year unset."""
    metrics = await _extract("2025 2024 2023 Total net sales 416,161 391,035")
    revenue = [m for m in metrics if m.metric_name == "revenue"]
    assert revenue
    assert all(m.year is None and not m.year_validated for m in revenue)


async def test_a_row_with_no_header_at_all_has_no_validated_year():
    metrics = await _extract("Diluted earnings per share $ 7.46 $ 6.08 $ 6.13", years=[2025])
    eps = [m for m in metrics if m.metric_name == "eps"]
    assert {m.value for m in eps} == {7.46, 6.08, 6.13}
    assert all(m.year is None and not m.year_validated for m in eps)  # not stamped with 2025


async def test_footnote_markers_do_not_shift_columns():
    metrics = await _extract(
        "2025 2024 2023 Total net sales $ 416,161 $ 391,035 $ 383,285 (1) Services net sales include x."
    )
    revenue = {y: m.value for y, m in _by(metrics, "revenue").items()}
    assert revenue == {2025: 416161.0, 2024: 391035.0, 2023: 383285.0}


async def test_prose_year_adjacent_to_value_is_validated_but_query_year_is_not():
    adjacent = await _extract("Revenue was $391 billion in fiscal 2024.", years=[2025])
    assert adjacent[0].year == 2024 and adjacent[0].year_validated

    guessed = await _extract("Net income was $99.8 billion for the year.", years=[2025])
    assert guessed[0].year == 2025 and not guessed[0].year_validated  # the query's year is a guess


# --- 3: unit handling ----------------------------------------------------------


async def test_unit_scale_comes_from_the_table_caption_and_is_never_guessed():
    millions = await _extract("(dollars in millions): 2025 2024 Total net sales $ 416,161 $ 391,035 x.")
    assert {m.unit for m in millions if m.metric_name == "revenue"} == {"usd_millions"}

    thousands = await _extract("(in thousands) 2025 2024 Net income $ 5,100 $ 4,900 x.")
    assert {m.unit for m in thousands if m.metric_name == "net_income"} == {"usd_thousands"}

    unstated = await _extract("2025 2024 Net income $ 5,100 $ 4,900 x.")
    assert {m.unit for m in unstated if m.metric_name == "net_income"} == {"usd"}


async def test_first_scale_in_a_mixed_caption_is_the_monetary_one():
    """"(In millions, except number of shares, which are reflected in
    thousands, ...)" — dollar rows are in millions, not thousands."""
    metrics = await _extract(INCOME_STATEMENT_AND_BALANCE_SHEET)
    assert {m.unit for m in metrics if m.metric_name in ("total_assets", "total_liabilities")} == {
        "usd_millions"
    }


async def test_per_share_values_do_not_take_the_statement_scale():
    metrics = await _extract(
        "(in millions, except per-share amounts) 2025 2024 Diluted earnings per share $ 7.46 $ 6.08 x."
    )
    assert {m.unit for m in metrics if m.metric_name == "eps"} == {"usd_per_share"}


async def test_percent_metric_reads_percent_cells_not_the_dollar_row():
    metrics = await _extract(
        "2025 2024 2023 Total gross margin $ 195,201 $ 180,683 $ 169,148 "
        "Total gross margin percentage 46.9% 46.2% 44.1%"
    )
    margins = [m for m in metrics if m.metric_name == "gross_margin"]
    assert {(m.year, m.value, m.unit) for m in margins} == {
        (2025, 46.9, "percent"),
        (2024, 46.2, "percent"),
        (2023, 44.1, "percent"),
    }


async def test_scale_and_header_are_recovered_from_the_previous_chunk(monkeypatch):
    """The chunker cut this chunk mid-table: its caption and year header live
    at the end of the previous chunk. The agent looks one chunk back."""
    import app.agents.extraction_agent as extraction_module

    async def fake_previous_tail(state, item):
        return "(dollars in millions): 2025 2024 2023"

    monkeypatch.setattr(extraction_module, "_preceding_chunk_tail", fake_previous_tail)
    state = _state([_item("Total net sales $ 416,161 $ 391,035 $ 383,285")])

    await run_extraction_agent(state)

    revenue = {m.year: m for m in state.extracted_metrics if m.metric_name == "revenue"}
    assert set(revenue) == {2025, 2024, 2023}
    assert all(m.unit == "usd_millions" and m.year_validated for m in revenue.values())
