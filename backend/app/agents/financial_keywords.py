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

# Margin metrics ARE percentages (unit="percent" is the correct reading for
# them); every other metric is a dollar amount, and a "percent" extraction
# under that name is a YoY-change annotation sitting next to the real
# figure in the source table ("$391B, up 6%"), not the metric itself.
# Shared by the Calculation Agent (grouping years for CAGR/growth) and the
# Report Agent (picking which extracted value answers a plain lookup) so
# both agree on which unit is the "real" one per metric.
PERCENT_METRICS = {"gross_margin", "operating_margin", "net_margin"}

# Per-share metrics are plain dollars per share: they never carry a
# magnitude word ("24 million"), a percent sign, or the statement's
# "in millions" scale.
PER_SHARE_METRICS = {"eps"}

# Extra exact row-label spellings a financial statement uses for a metric,
# beyond the bare keyword and its "total ..." form (see
# `extraction_agent._label_matches_metric`). Row extraction only accepts a
# table row whose ENTIRE label is one of these — never a longer label that
# merely contains a keyword ("Total cost of sales", "Total liabilities and
# shareholders' equity", "Percentage of total net sales").
METRIC_LABEL_EXTRAS: dict[str, list[str]] = {
    "revenue": ["revenues", "net revenues", "net revenue", "total revenues", "total net revenues"],
    "eps": ["earnings per common share", "net income per share", "net income per common share"],
}

# When one metric has several legitimately different values for the same
# year in the same table (basic vs. diluted EPS), the variant whose label
# contains this hint is the headline figure.
PREFERRED_LABEL_HINT: dict[str, str] = {"eps": "diluted"}
