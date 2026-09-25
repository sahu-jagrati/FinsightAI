import { render, screen, within } from "@testing-library/react";
import type * as React from "react";
import { describe, expect, it, vi } from "vitest";
import multiInsufficient from "@/lib/__fixtures__/apple-multi-insufficient.json";
import multiValidated from "@/lib/__fixtures__/apple-multi-validated.json";
import revenue from "@/lib/__fixtures__/apple-revenue.json";
import type { ReportResult } from "@/types/api";
import { ReportView } from "./report-view";

// jsdom has no layout, so recharts' ResponsiveContainer renders nothing.
// Swap in a shim that exposes the data the chart was given.
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  BarChart: ({ data }: { data: unknown }) => (
    <div data-testid="chart" data-points={JSON.stringify(data)} />
  ),
  Bar: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
}));

const asReport = (x: unknown) => x as ReportResult;

describe("ReportView financial comparison", () => {
  it("renders the real Apple revenue values with their unit and period", () => {
    render(<ReportView report={asReport(revenue)} />);
    const table = screen.getByRole("table");
    expect(within(table).getByText("USD, millions")).toBeInTheDocument();
    expect(within(table).getByText(/2025: 416,161/)).toBeInTheDocument();
    expect(within(table).getByText(/2024: 391,035/)).toBeInTheDocument();
    expect(within(table).getByText("+6.4%")).toBeInTheDocument();
    expect(screen.getByText("(2024→2025)")).toBeInTheDocument();
  });

  it("shows Insufficient data (never a number) for metrics without validated years", () => {
    render(<ReportView report={asReport(multiInsufficient)} />);
    const table = screen.getByRole("table");
    expect(within(table).getAllByText("Insufficient data")).toHaveLength(2);
    // EPS, the only validated metric, still renders
    expect(within(table).getByText(/2025: \$7\.46/)).toBeInTheDocument();
    // no calculation card is produced for the insufficient rows
    expect(screen.queryByText(/Total Liabilities — /)).not.toBeInTheDocument();
  });

  it("uses en-US grouping, not the viewer's locale", () => {
    render(<ReportView report={asReport(multiValidated)} />);
    expect(screen.getByText(/2025: 359,241/)).toBeInTheDocument();
    expect(screen.queryByText(/3,59,241/)).not.toBeInTheDocument();
  });

  it("chart, table and cards all show the same calculation values", () => {
    render(<ReportView report={asReport(multiValidated)} />);
    const points = JSON.parse(screen.getByTestId("chart").getAttribute("data-points")!) as {
      label: string;
    }[];
    const table = screen.getByRole("table");
    expect(points).toHaveLength(3);
    for (const p of points) {
      // every plotted value appears in the table's Result column AND as a card
      expect(within(table).getAllByText(p.label).length).toBeGreaterThan(0);
      expect(screen.getAllByText(p.label).length).toBeGreaterThanOrEqual(2);
    }
  });
});
