"use client";

import { AlertTriangle } from "lucide-react";
import * as React from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatPercent } from "@/lib/utils";
import {
  INSUFFICIENT_DATA,
  buildCalculationCards,
  buildChartData,
  buildDisplayRows,
} from "@/lib/report-data";
import type { Citation, ReportResult } from "@/types/api";
import { Badge } from "@/components/ui/badge";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/table";
import { CitationChip } from "@/components/research/citation-modal";

export function ReportView({ report }: { report: ReportResult }) {
  if (report.insufficient_evidence) {
    return (
      <div className="flex items-start gap-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 text-sm text-amber-300">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
        <span>{report.executive_summary}</span>
      </div>
    );
  }

  // One source of truth: the chart, the table and the calculation cards are
  // all views over the same validated rows (see lib/report-data.ts).
  const rows = buildDisplayRows(report);
  const chartData = buildChartData(rows);
  const cards = buildCalculationCards(rows);

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm leading-relaxed text-foreground">{report.executive_summary}</p>
        <Badge variant={report.confidence > 0.6 ? "success" : "warning"} className="shrink-0">
          {formatPercent(report.confidence, 0)} confidence
        </Badge>
      </div>

      {report.key_findings.length > 0 && (
        <div>
          <SectionLabel>Key findings</SectionLabel>
          <ul className="space-y-1.5">
            {report.key_findings.map((f, i) => (
              <li key={i} className="flex gap-2 text-sm text-foreground">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-indigo-400" />
                {f}
              </li>
            ))}
          </ul>
        </div>
      )}

      {chartData.length > 0 && (
        <div>
          <SectionLabel>Calculation comparison</SectionLabel>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis dataKey="name" stroke="#8b94a7" fontSize={11} />
                <YAxis stroke="#8b94a7" fontSize={11} tickFormatter={(v) => `${v}%`} />
                <Tooltip
                  formatter={(v) => `${Number(v).toFixed(1)}%`}
                  contentStyle={{
                    background: "#111827",
                    border: "1px solid #1f2937",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                />
                <Bar dataKey="value" fill="#6366f1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {rows.length > 0 && (
        <div>
          <SectionLabel>Financial comparison</SectionLabel>
          <Table>
            <Thead>
              <Tr>
                <Th>Company</Th>
                <Th>Metric</Th>
                <Th>Unit</Th>
                <Th>Values by year</Th>
                <Th>Result</Th>
              </Tr>
            </Thead>
            <Tbody>
              {rows.map((row) => (
                <Tr key={row.key}>
                  <Td className="font-medium">{row.company}</Td>
                  <Td className="text-muted">{row.metricLabel}</Td>
                  <Td className="text-muted">{row.unitLabel}</Td>
                  <Td className="text-muted">
                    {row.years.length > 0
                      ? row.years.map((y) => `${y.year}: ${y.value}`).join("  ·  ")
                      : "—"}
                  </Td>
                  <Td>
                    {row.calculation ? (
                      <span className="font-medium text-emerald-400">
                        {cards.find((c) => c.key === row.key)?.value}
                      </span>
                    ) : row.insufficient ? (
                      <span className="text-amber-400" title={row.insufficientReason ?? undefined}>
                        {INSUFFICIENT_DATA}
                      </span>
                    ) : (
                      "—"
                    )}
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </div>
      )}

      {cards.length > 0 && (
        <div>
          <SectionLabel>Calculations</SectionLabel>
          <div className="space-y-2">
            {cards.map((c) => (
              <div
                key={c.key}
                className="flex items-center justify-between rounded-md bg-white/[0.03] px-3 py-2 text-xs"
              >
                <div>
                  <div className="font-medium text-foreground">
                    {c.title}
                    {c.period && <span className="ml-1.5 text-muted">({c.period})</span>}
                  </div>
                  <div className="font-mono text-[11px] text-muted">{c.formula}</div>
                </div>
                <div className="font-mono text-sm font-semibold text-indigo-300">{c.value}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {report.citations.length > 0 && (
        <div>
          <SectionLabel>Sources</SectionLabel>
          <div className="flex flex-wrap gap-2">
            {report.citations.map((c, i) => (
              <CitationChip key={i} citation={c} index={i + 1} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">{children}</div>
  );
}

export type { Citation };
