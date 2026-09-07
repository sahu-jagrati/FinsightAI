import pytest

from app.services.calculations import (
    CalculationError,
    average_growth,
    cagr,
    difference,
    margin,
    percentage_change,
    percentage_point_difference,
    ratio,
    yoy_growth,
)


def test_cagr_matches_known_example():
    # Revenue 100 -> 150 over 3 years, from the spec's own worked example.
    result = cagr(100, 150, 3)
    assert result.result == pytest.approx((150 / 100) ** (1 / 3) - 1, rel=1e-9)
    assert result.result == pytest.approx(0.1447, abs=1e-3)


def test_cagr_zero_growth():
    result = cagr(100, 100, 5)
    assert result.result == pytest.approx(0.0)


def test_cagr_rejects_non_positive_beginning_value():
    with pytest.raises(CalculationError):
        cagr(0, 150, 3)
    with pytest.raises(CalculationError):
        cagr(-10, 150, 3)


def test_cagr_rejects_non_positive_periods():
    with pytest.raises(CalculationError):
        cagr(100, 150, 0)
    with pytest.raises(CalculationError):
        cagr(100, 150, -2)


def test_percentage_change():
    result = percentage_change(200, 250)
    assert result.result == pytest.approx(0.25)


def test_percentage_change_negative_direction():
    result = percentage_change(250, 200)
    assert result.result == pytest.approx(-0.2)


def test_percentage_change_rejects_zero_base():
    with pytest.raises(CalculationError):
        percentage_change(0, 100)


def test_yoy_growth_computes_each_consecutive_pair():
    values = {2022: 100, 2023: 110, 2024: 121}
    growth = yoy_growth(values)
    assert set(growth.keys()) == {2023, 2024}
    assert growth[2023].result == pytest.approx(0.10)
    assert growth[2024].result == pytest.approx(0.10)


def test_yoy_growth_skips_non_consecutive_years():
    values = {2020: 100, 2024: 200}
    with pytest.raises(CalculationError):
        yoy_growth(values)


def test_yoy_growth_requires_two_years():
    with pytest.raises(CalculationError):
        yoy_growth({2024: 100})


def test_average_growth():
    values = {2022: 100, 2023: 110, 2024: 121}
    result = average_growth(values)
    assert result.result == pytest.approx(0.10)


def test_margin():
    result = margin(25, 100, label="net margin")
    assert result.result == pytest.approx(0.25)


def test_margin_rejects_zero_denominator():
    with pytest.raises(CalculationError):
        margin(25, 0)


def test_ratio_rejects_zero_divisor():
    with pytest.raises(CalculationError):
        ratio(1, 0)


def test_difference():
    assert difference(150, 100).result == 50


def test_percentage_point_difference():
    result = percentage_point_difference(0.32, 0.28)
    assert result.result == pytest.approx(0.04)
