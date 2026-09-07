import pytest

from app.rag.ingestion.metadata_extractor import extract_year


@pytest.mark.parametrize(
    "period,expected",
    [
        ("2025", 2025),
        ("Q4 2025", 2025),
        ("FY2024", 2024),
        ("fiscal year 2023", 2023),
        (None, None),
        ("", None),
        ("N/A", None),
    ],
)
def test_extract_year(period, expected):
    assert extract_year(period) == expected
