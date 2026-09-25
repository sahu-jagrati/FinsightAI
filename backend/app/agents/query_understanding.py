"""Query understanding (Section 9) — figures out companies, metrics,
years, requested document types, and requested operations (CAGR,
comparison, growth, margin...) BEFORE retrieval runs, so the supervisor can
decide which agents are actually needed and the retrieval agent can filter
instead of searching blind.

Deterministic (regex/keyword matching against known companies), not an LLM
call — Section 35: "Use code for... deterministic transformations". It's
also strictly more reliable for this than an LLM call would be when
`LLM_PROVIDER=mock`, and just as fast/free with a real provider configured.
"""

import re

from app.agents.financial_keywords import METRIC_KEYWORDS
from app.agents.state import QueryUnderstanding

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_YEAR_RANGE_RE = re.compile(r"\b((19|20)\d{2})\s*(?:to|-|–|—|through)\s*((19|20)\d{2})\b")

# Query phrasing is looser than document phrasing ("sales", "assets",
# "liabilities" alone are common in questions but too ambiguous to trust
# as a standalone match inside a wall of document text), so the query-side
# keyword list extends the shared one with a few query-only synonyms.
_QUERY_METRIC_KEYWORDS: dict[str, list[str]] = {
    **METRIC_KEYWORDS,
    "revenue": METRIC_KEYWORDS["revenue"] + ["top line"],
    "total_assets": METRIC_KEYWORDS["total_assets"] + ["assets"],
    "total_liabilities": METRIC_KEYWORDS["total_liabilities"] + ["liabilities"],
    "total_expenses": METRIC_KEYWORDS["total_expenses"] + ["expenses"],
}

_OPERATION_KEYWORDS: dict[str, list[str]] = {
    "cagr": ["cagr", "compound annual growth"],
    "growth": [
        "growth",
        "grew",
        "increase",
        "yoy",
        "year over year",
        "year-over-year",
        # "Calculate the percentage change ..." is a very common way to
        # phrase a growth request without using the word "growth" at all —
        # found live: this exact phrasing on a real Apple 10-K query left
        # `operations` as just `["summary"]` (matched by "reasons"),
        # `wants_calculation` false, and the Calculation Agent silently
        # skipped even though retrieval/extraction had everything needed.
        "percentage change",
        "percent change",
        "% change",
        "pct change",
        "rate of change",
    ],
    "margin": ["margin"],
    "comparison": ["compare", "comparison", "versus", " vs ", " vs. "],
    "summary": ["summarize", "summary", "overview", "what caused", "why did", "reasons"],
    "ratio": ["ratio"],
}

_DOCUMENT_TYPE_KEYWORDS: dict[str, list[str]] = {
    "annual_report": ["annual report", "10-k", "10k"],
    "quarterly_report": ["quarterly report", "10-q", "10q", "quarter"],
    "sec_filing": ["sec filing", "filing"],
    "earnings_report": ["earnings report", "earnings release", "earnings call"],
    "news": ["news", "article"],
}


def _expand_year_range(text: str) -> list[int]:
    years: set[int] = set()
    for match in _YEAR_RANGE_RE.finditer(text):
        start, end = int(match.group(1)), int(match.group(3))
        if start <= end and end - start <= 30:
            years.update(range(start, end + 1))
    return sorted(years)


async def understand_query(query: str, known_companies: list[str]) -> QueryUnderstanding:
    lowered = query.lower()

    companies = [c for c in known_companies if c.lower() in lowered]

    # `.findall` on a pattern with a capturing group returns only the group
    # text ("19"/"20"), so pull full 4-digit matches via `.finditer` instead.
    years = {int(m.group()) for m in _YEAR_RE.finditer(query)}
    years.update(_expand_year_range(lowered))

    metrics = [
        metric
        for metric, keywords in _QUERY_METRIC_KEYWORDS.items()
        if any(kw in lowered for kw in keywords)
    ]

    operations = [
        op for op, keywords in _OPERATION_KEYWORDS.items() if any(kw in lowered for kw in keywords)
    ]

    document_types = [
        dt for dt, keywords in _DOCUMENT_TYPE_KEYWORDS.items() if any(kw in lowered for kw in keywords)
    ]

    is_comparison = "comparison" in operations or len(companies) >= 2

    return QueryUnderstanding(
        companies=companies,
        metrics=metrics,
        years=sorted(years),
        document_types=document_types,
        operations=operations,
        is_comparison=is_comparison,
    )
