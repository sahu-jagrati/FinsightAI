"""Deterministic financial calculations (Section 13).

The LLM decides *what* to calculate; this module is the only thing that
actually does arithmetic (Section 35 — "Never rely on the LLM to perform
important financial calculations itself"). Every function returns a
`CalculationResult` carrying the formula and inputs alongside the number,
so the Report Generation Agent can show its work rather than presenting a
bare figure.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from app.core.exceptions import AppError


class CalculationError(AppError):
    code = "calculation_error"


class Operation(StrEnum):
    CAGR = "cagr"
    PERCENTAGE_CHANGE = "percentage_change"
    YOY_GROWTH = "yoy_growth"
    AVERAGE_GROWTH = "average_growth"
    MARGIN = "margin"
    RATIO = "ratio"
    DIFFERENCE = "difference"
    PERCENTAGE_POINT_DIFFERENCE = "percentage_point_difference"


@dataclass
class CalculationResult:
    operation: Operation
    result: float
    formula: str
    inputs: dict = field(default_factory=dict)


def cagr(beginning_value: float, ending_value: float, periods: float) -> CalculationResult:
    """CAGR = (Ending / Beginning)^(1/n) - 1"""
    if periods <= 0:
        raise CalculationError("CAGR requires a positive number of periods.")
    if beginning_value <= 0:
        raise CalculationError(
            "CAGR requires a positive beginning value (got "
            f"{beginning_value}) — the growth rate is undefined otherwise."
        )
    if ending_value < 0:
        raise CalculationError("CAGR requires a non-negative ending value.")

    result = (ending_value / beginning_value) ** (1 / periods) - 1
    return CalculationResult(
        operation=Operation.CAGR,
        result=result,
        formula="(Ending Value / Beginning Value) ^ (1 / n) - 1",
        inputs={
            "beginning_value": beginning_value,
            "ending_value": ending_value,
            "periods": periods,
        },
    )


def percentage_change(old_value: float, new_value: float) -> CalculationResult:
    if old_value == 0:
        raise CalculationError("Percentage change is undefined when the starting value is 0.")

    result = (new_value - old_value) / abs(old_value)
    return CalculationResult(
        operation=Operation.PERCENTAGE_CHANGE,
        result=result,
        formula="(New Value - Old Value) / |Old Value|",
        inputs={"old_value": old_value, "new_value": new_value},
    )


def yoy_growth(values_by_year: dict[int, float]) -> dict[int, CalculationResult]:
    """Year-over-year growth for every year that has a prior year in the
    input. Returns a dict keyed by the LATER year in each pair."""
    if len(values_by_year) < 2:
        raise CalculationError("YoY growth requires at least two years of data.")

    results: dict[int, CalculationResult] = {}
    for year in sorted(values_by_year):
        prev_year = year - 1
        if prev_year in values_by_year:
            change = percentage_change(values_by_year[prev_year], values_by_year[year])
            results[year] = CalculationResult(
                operation=Operation.YOY_GROWTH,
                result=change.result,
                formula=change.formula,
                inputs={"year": year, **change.inputs},
            )
    if not results:
        raise CalculationError("No consecutive years found to compute YoY growth.")
    return results


def average_growth(values_by_year: dict[int, float]) -> CalculationResult:
    growth = yoy_growth(values_by_year)
    rates = [r.result for r in growth.values()]
    result = sum(rates) / len(rates)
    return CalculationResult(
        operation=Operation.AVERAGE_GROWTH,
        result=result,
        formula="mean(YoY growth rates)",
        inputs={"years": sorted(growth.keys()), "rates": rates},
    )


def margin(numerator: float, denominator: float, *, label: str = "margin") -> CalculationResult:
    if denominator == 0:
        raise CalculationError(f"Cannot compute {label}: denominator is 0.")

    result = numerator / denominator
    return CalculationResult(
        operation=Operation.MARGIN,
        result=result,
        formula=f"{label} = numerator / denominator",
        inputs={"numerator": numerator, "denominator": denominator, "label": label},
    )


def ratio(a: float, b: float, *, label: str = "ratio") -> CalculationResult:
    if b == 0:
        raise CalculationError(f"Cannot compute {label}: divisor is 0.")

    result = a / b
    return CalculationResult(
        operation=Operation.RATIO,
        result=result,
        formula=f"{label} = a / b",
        inputs={"a": a, "b": b, "label": label},
    )


def difference(a: float, b: float) -> CalculationResult:
    return CalculationResult(
        operation=Operation.DIFFERENCE,
        result=a - b,
        formula="a - b",
        inputs={"a": a, "b": b},
    )


def percentage_point_difference(a_pct: float, b_pct: float) -> CalculationResult:
    """For comparing two already-percentage figures (e.g. two margins),
    where the "difference" is expressed in percentage points, not a
    percentage of a percentage."""
    return CalculationResult(
        operation=Operation.PERCENTAGE_POINT_DIFFERENCE,
        result=a_pct - b_pct,
        formula="a_pct - b_pct (in percentage points)",
        inputs={"a_pct": a_pct, "b_pct": b_pct},
    )
