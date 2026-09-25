import { describe, expect, it } from "vitest";
import multiInsufficient from "@/lib/__fixtures__/apple-multi-insufficient.json";
import multiValidated from "@/lib/__fixtures__/apple-multi-validated.json";
import revenue from "@/lib/__fixtures__/apple-revenue.json";
import {
  INSUFFICIENT_DATA,
  buildCalculationCards,
  buildChartData,
  buildDisplayRows,
  formatCalculation,
  formatValue,
  unitLabel,
} from "@/lib/report-data";
import type { ReportResult } from "@/types/api";

// Fixtures are REAL outputs: `apple-revenue` / `apple-multi-insufficient`
// are `POST /api/analyze` results for the uploaded Apple 10-K;
// `apple-multi-validated` is the real Extraction -> Calculation -> Report
// pipeline run over the stored balance-sheet/income-statement chunk.
const asReport = (x: unknown) => x as ReportResult;

describe("number formatting", () => {
  it("always groups thousands the en-US way (never 3,59,241)", () => {
    expect(formatValue(359241, "usd_millions")).toBe("359,241");
    expect(formatValue(359241, "usd_millions")).not.toContain("3,59");
  });

  it("keeps per-share values at two decimals and percents as percents", () => {
    expect(formatValue(7.46, "usd_per_share")).toBe("$7.46");
    expect(formatValue(46.9, "percent")).toBe("46.9%");
  });

  it("labels units exactly as reported", () => {
    expect(unitLabel("usd_millions")).toBe("USD, millions");
    expect(unitLabel("usd_thousands")).toBe("USD, thousands");
    expect(unitLabel("usd_per_share")).toBe("USD per share");
  });

  it("formats calculations by operation - a percentage-point change is not a percentage", () => {
    const pct = { operation: "percentage_change", result: 0.06426, formula: "", inputs: {} };
    const pp = { operation: "percentage_point_difference", result: 1.5, formula: "", inputs: {} };
    expect(formatCalculation(pct)).toBe("+6.4%");
    expect(formatCalculation(pp)).toBe("+1.5 pp");
  });
});

describe("Apple revenue report (real API output)", () => {
  const rows = buildDisplayRows(asReport(revenue));

  it("pairs each year with its own value, in the reported unit", () => {
    expect(rows).toHaveLength(1);
    expect(rows[0].unit).toBe("usd_millions");
    expect(rows[0].years).toEqual([
      { year: "2025", value: "416,161" },
      { year: "2024", value: "391,035" },
    ]);
    expect(rows[0].insufficient).toBe(false);
  });

  it("carries the period the calculation covers", () => {
    const [card] = buildCalculationCards(rows);
    expect(card.period).toBe("2024→2025");
    expect(card.value).toBe("+6.4%");
  });
});

describe("missing-year / no-data handling (real API output)", () => {
  const rows = buildDisplayRows(asReport(multiInsufficient));
  const byMetric = Object.fromEntries(rows.map((r) => [r.metric, r]));

  it("marks a metric with no validated data as Insufficient data, without inventing values", () => {
    for (const metric of ["total_assets", "total_liabilities"]) {
      expect(byMetric[metric].insufficient).toBe(true);
      expect(byMetric[metric].years).toEqual([]);
      expect(byMetric[metric].calculation).toBeNull();
      expect(byMetric[metric].insufficientReason).toContain(INSUFFICIENT_DATA);
    }
  });

  it("marks a single validated year as insufficient rather than computing", () => {
    const report = asReport({
      ...multiInsufficient,
      comparison_table: [
        {
          company: "Apple",
          metric: "total_liabilities",
          values_by_year: { "2025": 285508 },
          calculation: null,
          unit: "usd_millions",
          insufficient_reason: null,
        },
      ],
    });
    const [row] = buildDisplayRows(report);
    expect(row.insufficient).toBe(true);
    expect(row.years).toEqual([{ year: "2025", value: "285,508" }]);
  });

  it("does not turn insufficient rows into cards or chart bars", () => {
    expect(buildCalculationCards(rows)).toHaveLength(1);
    expect(buildChartData(rows)).toHaveLength(1);
    expect(buildChartData(rows)[0].name).toContain("EPS");
  });
});

describe("chart / table / card consistency (real pipeline output)", () => {
  const rows = buildDisplayRows(asReport(multiValidated));
  const cards = buildCalculationCards(rows);
  const chart = buildChartData(rows);

  it("shows the corrected balance-sheet and EPS values", () => {
    const by = Object.fromEntries(rows.map((r) => [r.metric, r]));
    expect(by.eps.years).toEqual([
      { year: "2025", value: "$7.46" },
      { year: "2024", value: "$6.08" },
    ]);
    expect(by.total_liabilities.years).toEqual([
      { year: "2025", value: "285,508" },
      { year: "2024", value: "308,030" },
    ]);
    expect(by.total_assets.years[0]).toEqual({ year: "2025", value: "359,241" });
  });

  it("derives cards and chart from the same rows, with identical numbers", () => {
    expect(cards).toHaveLength(rows.filter((r) => r.calculation).length);
    expect(chart).toHaveLength(cards.length);
    cards.forEach((card, i) => {
      // the bar's displayed label is exactly the card's value
      expect(chart[i].label).toBe(card.value);
    });
  });

  it("never plots percentage-point results next to growth rates", () => {
    const report = asReport({
      ...multiValidated,
      comparison_table: [
        {
          company: "Apple",
          metric: "gross_margin",
          values_by_year: { "2025": 46.9, "2024": 46.2 },
          calculation: {
            operation: "percentage_point_difference",
            result: 0.7,
            formula: "a_pct - b_pct",
            inputs: { begin_year: 2024, end_year: 2025 },
          },
          unit: "percent",
          insufficient_reason: null,
        },
      ],
    });
    const r = buildDisplayRows(report);
    expect(buildCalculationCards(r)[0].value).toBe("+0.7 pp");
    expect(buildChartData(r)).toEqual([]);
  });
});
