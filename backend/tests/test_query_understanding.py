import pytest

from app.agents.query_understanding import understand_query

pytestmark = pytest.mark.asyncio

KNOWN_COMPANIES = ["Apple", "Microsoft", "Tesla", "Toyota", "Amazon", "Walmart"]


async def test_detects_companies_metric_and_years():
    u = await understand_query(
        "Compare Apple's and Microsoft's revenue growth from 2022 to 2025.", KNOWN_COMPANIES
    )
    assert set(u.companies) == {"Apple", "Microsoft"}
    assert "revenue" in u.metrics
    assert u.years == [2022, 2023, 2024, 2025]
    assert "growth" in u.operations
    assert u.is_comparison is True


async def test_detects_cagr_request():
    u = await understand_query("Calculate Microsoft's 3-year revenue CAGR.", KNOWN_COMPANIES)
    assert u.companies == ["Microsoft"]
    assert "cagr" in u.operations
    assert u.is_comparison is False


async def test_detects_margin_comparison():
    u = await understand_query(
        "Compare the net income margins of Amazon and Walmart.", KNOWN_COMPANIES
    )
    assert set(u.companies) == {"Amazon", "Walmart"}
    assert "net_margin" in u.metrics
    assert "margin" in u.operations
    assert u.is_comparison is True


async def test_single_year_no_range():
    u = await understand_query("What was Tesla's operating margin in 2024?", KNOWN_COMPANIES)
    assert u.years == [2024]
    assert u.companies == ["Tesla"]


async def test_no_companies_mentioned():
    u = await understand_query("Summarize the major risks in the latest annual report.", KNOWN_COMPANIES)
    assert u.companies == []
    assert "summary" in u.operations
