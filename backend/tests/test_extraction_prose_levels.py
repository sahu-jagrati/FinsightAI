"""Prose extraction only counts a number as a metric's LEVEL when the
sentence states it directly. Every negative case below is a real sentence
from the Microsoft / Walmart / Amazon 10-Ks in the database that the old
nearest-keyword logic turned into a bogus metric value."""

import uuid

import pytest

from app.agents.extraction_agent import run_extraction_agent
from app.agents.state import EvidenceItem, QueryUnderstanding, ResearchState

pytestmark = pytest.mark.asyncio


async def _extract(content: str, company: str = "Microsoft"):
    item = EvidenceItem(
        chunk_id=uuid.uuid4(),
        content=content,
        company=company,
        document_filename="f.html",
        page_number=1,
        section=None,
        score=0.9,
    )
    state = ResearchState(
        query="q",
        db=None,
        llm=None,
        embedding_service=None,
        reranker=None,
        session_factory=lambda: None,
        understanding=QueryUnderstanding(),
        evidence=[item],
    )
    await run_extraction_agent(state)
    return state.extracted_metrics


@pytest.mark.parametrize(
    "sentence",
    [
        # a CHANGE in revenue, not revenue
        "Fiscal Year 2026 Compared with Fiscal Year 2025 Revenue increased $50.1 billion or 18% driven by growth in Microsoft Cloud.",
        "Microsoft 365 Consumer products and cloud services revenue increased $1.8 billion or 24%.",
        # an IMPACT on operating income
        "Changes in foreign exchange rates negatively impacted operating income by $204 million in 2025.",
        # a one-off charge mentioned near the keyword
        "Operating income for 2025 includes charges of $2.5 billion we recorded in Q3 2025 related to the settlement.",
        # a SEGMENT's net sales, not the company's
        "Walmart U.S. had net sales of $483.0 billion for fiscal 2026, representing 68% of our fiscal 2026 consolidated net sales.",
        # a forecast
        "Operating income is expected to be between $16.5 billion and $21.5 billion, compared with $18.4 billion.",
        # a different line item
        "The Company had total deferred revenue of $13.7 billion and revenue grew 6% in 2025.",
    ],
)
async def test_changes_impacts_segments_and_forecasts_are_not_metric_levels(sentence):
    metrics = await _extract(sentence)
    assert metrics == [], [(m.metric_name, m.value, m.unit) for m in metrics]


async def test_a_direct_company_level_statement_is_still_extracted():
    metrics = await _extract(
        "During fiscal 2026, we generated total revenues of $713.2 billion, which primarily "
        "comprised net sales of $706.4 billion.",
        company="Walmart",
    )
    revenue = [m for m in metrics if m.metric_name == "revenue"]
    assert [(m.value, m.unit, m.year, m.year_validated) for m in revenue] == [
        (713.2, "usd_billions", 2026, True)
    ]


async def test_chained_values_of_one_statement_each_keep_their_own_year():
    metrics = await _extract(
        "Operating income was $68.6 billion in 2024 and $80.0 billion in 2025."
    )
    by_year = {m.year: m.value for m in metrics if m.metric_name == "operating_income"}
    assert by_year == {2024: 68.6, 2025: 80.0}


async def test_possessive_company_subject_is_company_level():
    metrics = await _extract("Apple's revenue for fiscal 2025 was $416 billion.", company="Apple")
    assert [(m.metric_name, m.value, m.year) for m in metrics] == [("revenue", 416.0, 2025)]
