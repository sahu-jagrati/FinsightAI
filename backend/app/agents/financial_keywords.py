"""Metric name <-> phrasing keywords, shared by query understanding
(Section 9) and financial extraction (Section 12) so the two agree on
vocabulary."""

METRIC_KEYWORDS: dict[str, list[str]] = {
    "revenue": ["revenue", "net sales", "total sales", "sales"],
    "net_income": ["net income", "net profit", "net earnings"],
    "operating_income": ["operating income", "operating profit"],
    "eps": ["earnings per share", "eps"],
    "total_assets": ["total assets"],
    "total_liabilities": ["total liabilities"],
    "operating_cash_flow": ["operating cash flow", "cash flow from operations"],
    "free_cash_flow": ["free cash flow"],
    "total_expenses": ["total operating expenses", "total expenses", "operating expenses"],
    "gross_margin": ["gross margin"],
    "operating_margin": ["operating margin"],
    "net_margin": ["net margin", "net income margin", "profit margin"],
}
