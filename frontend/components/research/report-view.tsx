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
import { formatPercent, titleCase } from "@/lib/utils";
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

  const calcRows = report.comparison_table.filter((r) => r.calculation);
  const chartData = calcRows.map((r) => ({
    name: `${r.company} · ${titleCase(r.metric)}`,
    value: r.calculation!.result,
  }));

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
                <YAxis
                  stroke="#8b94a7"
                  fontSize={11}
                  tickFormatter={(v) => formatPercent(v, 0)}
                />
                <Tooltip
                  formatter={(v) => formatPercent(Number(v))}
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

      {report.comparison_table.length > 0 && (
        <div>
          <SectionLabel>Financial comparison</SectionLabel>
          <Table>
            <Thead>
              <Tr>
                <Th>Company</Th>
                <Th>Metric</Th>
                <Th>Values by year</Th>
                <Th>Result</Th>
              </Tr>
            </Thead>
            <Tbody>
              {report.comparison_table.map((row, i) => (
                <Tr key={i}>
                  <Td className="font-medium">{row.company}</Td>
                  <Td className="text-muted">{titleCase(row.metric)}</Td>
                  <Td className="text-muted">
                    {Object.entries(row.values_by_year)
                      .map(([y, v]) => `${y}: ${v.toLocaleString()}`)
                      .join("  ·  ")}
                  </Td>
                  <Td>
                    {row.calculation ? (
                      <span className="font-medium text-emerald-400">
                        {formatPercent(row.calculation.result)}
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

      {report.calculations.length > 0 && (
        <div>
          <SectionLabel>Calculations</SectionLabel>
          <div className="space-y-2">
            {report.calculations.map((c, i) => (
              <div
                key={i}
                className="flex items-center justify-between rounded-md bg-white/[0.03] px-3 py-2 text-xs"
              >
                <div>
                  <div className="font-medium text-foreground">{titleCase(c.operation)}</div>
                  <div className="font-mono text-[11px] text-muted">{c.formula}</div>
                </div>
                <div className="font-mono text-sm font-semibold text-indigo-300">
                  {formatPercent(c.result)}
                </div>
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
