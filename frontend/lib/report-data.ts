import type { CalculationResult, ComparisonRow, ReportResult } from "@/types/api";
import { titleCase } from "@/lib/utils";

/**
 * The ONE place a report's financial numbers are interpreted for display.
 * The Financial Comparison table, the calculation cards and the chart all
 * read rows through here, so they cannot disagree with each other: each is
 * a view over the same validated `comparison_table` rows the backend
 * produced (and nothing else — `report.calculations` is never rendered
 * independently, because a calculation with no row has no validated
 * metric/years/unit behind it).
 */

export const INSUFFICIENT_DATA = "Insufficient data";

const UNIT_LABELS: Record<string, string> = {
  usd: "USD",
  usd_thousands: "USD, thousands",
  usd_millions: "USD, millions",
  usd_billions: "USD, billions",
  usd_per_share: "USD per share",
  percent: "%",
};

const PERCENT_SHAPED_OPERATIONS = new Set([
  "cagr",
  "percentage_change",
  "yoy_growth",
  "average_growth",
  "margin",
]);

const OPERATION_LABELS: Record<string, string> = {
  cagr: "CAGR",
  percentage_change: "Percentage change",
  yoy_growth: "YoY growth",
  average_growth: "Average YoY growth",
  margin: "Margin",
  ratio: "Ratio",
  difference: "Difference",
  percentage_point_difference: "Change in percentage points",
};

/** Fixed en-US grouping — the browser's default locale would render
 * 359,241 as "3,59,241" for en-IN viewers. */
export function formatNumber(value: number, maxFractionDigits = 2): string {
  return value.toLocaleString("en-US", { maximumFractionDigits: maxFractionDigits });
}

export function unitLabel(unit: string | undefined): string {
  return UNIT_LABELS[unit ?? "usd"] ?? unit ?? "";
}

/** A value exactly as reported: the number in the row's unit, no rescaling
 * ("416,161" under "USD, millions"), with $ / % only where the unit is. */
export function formatValue(value: number, unit: string | undefined): string {
  if (unit === "percent") return `${formatNumber(value, 1)}%`;
  if (unit === "usd_per_share") return `$${value.toFixed(2)}`;
  return formatNumber(value);
}

export function formatCalculation(c: CalculationResult): string {
  if (PERCENT_SHAPED_OPERATIONS.has(c.operation)) {
    const pct = (c.result * 100).toFixed(1);
    return c.operation === "margin" || c.result < 0 ? `${pct}%` : `+${pct}%`;
  }
  if (c.operation === "percentage_point_difference") {
    return `${c.result >= 0 ? "+" : ""}${c.result.toFixed(1)} pp`;
  }
  if (c.operation === "ratio") return `${c.result.toFixed(2)}x`;
  return formatNumber(c.result);
}

export function operationLabel(c: CalculationResult): string {
  return OPERATION_LABELS[c.operation] ?? titleCase(c.operation);
}

export function metricLabel(metric: string): string {
  return metric === "eps" ? "EPS" : titleCase(metric);
}

export function calculationPeriod(c: CalculationResult): string | null {
  const begin = c.inputs?.begin_year;
  const end = c.inputs?.end_year;
  if (typeof begin === "number" && typeof end === "number") {
    return begin === end ? String(end) : `${begin}→${end}`;
  }
  return null;
}

export interface DisplayRow {
  key: string;
  company: string;
  metric: string;
  metricLabel: string;
  unit: string;
  unitLabel: string;
  years: { year: string; value: string }[];
  calculation: CalculationResult | null;
  /** True whenever no validated calculation is available for this row. */
  insufficient: boolean;
  insufficientReason: string | null;
}

/** Every row of the comparison table, ready to render. A row without a
 * calculation is "insufficient" only when the backend said so or it has
 * fewer than two validated years; a plain multi-year lookup that simply
 * didn't ask for a calculation is not marked insufficient. */
export function buildDisplayRows(report: ReportResult): DisplayRow[] {
  return report.comparison_table.map((row: ComparisonRow, i) => {
    const years = Object.entries(row.values_by_year)
      .sort(([a], [b]) => Number(b) - Number(a))
      .map(([year, value]) => ({ year, value: formatValue(value, row.unit) }));
    const insufficient =
      !row.calculation && (Boolean(row.insufficient_reason) || years.length < 2);
    return {
      key: `${row.company}-${row.metric}-${i}`,
      company: row.company,
      metric: row.metric,
      metricLabel: metricLabel(row.metric),
      unit: row.unit ?? "usd",
      unitLabel: unitLabel(row.unit),
      years,
      calculation: row.calculation,
      insufficient,
      insufficientReason:
        row.insufficient_reason ?? (insufficient ? "Only one validated year available" : null),
    };
  });
}

export interface CalculationCard {
  key: string;
  title: string;
  period: string | null;
  value: string;
  formula: string;
}

/** Calculation cards — derived from the SAME rows as the table, so a card
 * can never show a number the table doesn't. */
export function buildCalculationCards(rows: DisplayRow[]): CalculationCard[] {
  return rows
    .filter((r) => r.calculation)
    .map((r) => ({
      key: r.key,
      title: `${r.company} · ${r.metricLabel} — ${operationLabel(r.calculation!)}`,
      period: calculationPeriod(r.calculation!),
      value: formatCalculation(r.calculation!),
      formula: r.calculation!.formula,
    }));
}

export interface ChartPoint {
  name: string;
  /** Percent (already ×100) — the same number the table/card shows. */
  value: number;
  label: string;
}

/** Chart bars: one per validated percent-shaped calculation in the table.
 * Percentage-point and dollar results are on a different scale and are
 * deliberately not plotted next to growth rates. */
export function buildChartData(rows: DisplayRow[]): ChartPoint[] {
  return rows
    .filter((r) => r.calculation && PERCENT_SHAPED_OPERATIONS.has(r.calculation.operation))
    .map((r) => {
      const period = calculationPeriod(r.calculation!);
      return {
        name: `${r.company} · ${r.metricLabel}${period ? ` (${period})` : ""}`,
        value: Number((r.calculation!.result * 100).toFixed(2)),
        label: formatCalculation(r.calculation!),
      };
    });
}
