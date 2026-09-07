"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, FileText } from "lucide-react";
import Link from "next/link";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getCompany, getCompanyMetrics, listDocuments } from "@/lib/api-client";
import { formatDate, titleCase } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/table";
import { DocumentStatusBadge } from "@/components/documents/status-badge";

const CHART_COLORS = ["#6366f1", "#10b981", "#f59e0b", "#38bdf8", "#f43f5e"];

export function CompanyDetail({ companyId }: { companyId: string }) {
  const companyQuery = useQuery({
    queryKey: ["company", companyId],
    queryFn: () => getCompany(companyId),
  });
  const metricsQuery = useQuery({
    queryKey: ["company-metrics", companyId],
    queryFn: () => getCompanyMetrics(companyId),
  });
  const documentsQuery = useQuery({
    queryKey: ["documents", "company", companyId],
    queryFn: () => listDocuments({ company_id: companyId, limit: 50 }),
  });

  if (companyQuery.isLoading) {
    return (
      <div className="mx-auto max-w-6xl space-y-6 p-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  const company = companyQuery.data;
  if (!company) {
    return <div className="p-6 text-sm text-muted">Company not found.</div>;
  }

  // Combine all metric series onto one chart timeline, keyed by year.
  const series = metricsQuery.data ?? [];
  const yearsSet = new Set<number>();
  series.forEach((s) => s.points.forEach((p) => yearsSet.add(p.year)));
  const chartData = Array.from(yearsSet)
    .sort()
    .map((year) => {
      const row: Record<string, number | string> = { year };
      series.forEach((s) => {
        const point = s.points.find((p) => p.year === year);
        if (point) row[s.metric_name] = point.value;
      });
      return row;
    });

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <Link href="/companies" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-foreground">
        <ArrowLeft className="h-3.5 w-3.5" /> Companies
      </Link>

      <div>
        <h1 className="text-xl font-semibold text-foreground">{company.name}</h1>
        <p className="text-sm text-muted">
          {company.ticker ?? "No ticker"} {company.industry ? `· ${company.industry}` : ""}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Financial metric trends</CardTitle>
        </CardHeader>
        <CardContent className="h-72 pt-0">
          {chartData.length === 0 ? (
            <div className="flex h-full items-center justify-center text-xs text-muted">
              No dated financial metrics extracted yet for {company.name}. Run a research
              query mentioning {company.name} to populate this chart.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis dataKey="year" stroke="#8b94a7" fontSize={12} />
                <YAxis stroke="#8b94a7" fontSize={12} />
                <Tooltip
                  contentStyle={{
                    background: "#111827",
                    border: "1px solid #1f2937",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} formatter={(v) => titleCase(String(v))} />
                {series.map((s, i) => (
                  <Line
                    key={s.metric_name}
                    type="monotone"
                    dataKey={s.metric_name}
                    stroke={CHART_COLORS[i % CHART_COLORS.length]}
                    strokeWidth={2}
                    dot={{ r: 3 }}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Documents ({documentsQuery.data?.total ?? 0})</CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          {!documentsQuery.data || documentsQuery.data.items.length === 0 ? (
            <p className="text-xs text-muted">No documents for this company yet.</p>
          ) : (
            <Table>
              <Thead>
                <Tr>
                  <Th>Document</Th>
                  <Th>Type</Th>
                  <Th>Period</Th>
                  <Th>Status</Th>
                  <Th>Uploaded</Th>
                </Tr>
              </Thead>
              <Tbody>
                {documentsQuery.data.items.map((d) => (
                  <Tr key={d.id}>
                    <Td className="flex items-center gap-2">
                      <FileText className="h-3.5 w-3.5 text-muted" />
                      {d.original_filename}
                    </Td>
                    <Td className="text-muted">{titleCase(d.document_type)}</Td>
                    <Td className="text-muted">{d.reporting_period ?? "—"}</Td>
                    <Td>
                      <DocumentStatusBadge status={d.status} />
                    </Td>
                    <Td className="text-muted">{formatDate(d.created_at)}</Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
