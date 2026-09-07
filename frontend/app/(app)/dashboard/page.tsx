"use client";

import { useQuery } from "@tanstack/react-query";
import {
  BarChart3,
  Building2,
  Database,
  FileText,
  Gauge,
  Layers,
  Sparkles,
  Zap,
} from "lucide-react";
import Link from "next/link";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getDashboardStats, listMetrics } from "@/lib/api-client";
import { formatDate, formatDuration, formatPercent, titleCase } from "@/lib/utils";
import { StatCard } from "@/components/dashboard/stat-card";
import { DocumentStatusBadge } from "@/components/documents/status-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/table";

export default function DashboardPage() {
  const statsQuery = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: getDashboardStats,
    refetchInterval: 30_000,
  });

  const metricsQuery = useQuery({
    queryKey: ["metrics", "recent"],
    queryFn: () => listMetrics({}),
  });

  const stats = statsQuery.data;

  const statusChartData = stats
    ? Object.entries(stats.documents_by_status).map(([status, count]) => ({
        status: titleCase(status),
        count,
      }))
    : [];

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Dashboard</h1>
        <p className="text-sm text-muted">
          Real-time overview of ingested documents, indexing, and research activity.
        </p>
      </div>

      {statsQuery.isLoading && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      )}

      {statsQuery.isError && (
        <Card>
          <CardContent className="p-5 text-sm text-rose-400">
            Couldn&apos;t load dashboard stats — is the backend running?
          </CardContent>
        </Card>
      )}

      {stats && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            <StatCard label="Documents" value={String(stats.documents_total)} icon={FileText} accent="indigo" />
            <StatCard label="Companies Tracked" value={String(stats.companies_total)} icon={Building2} accent="sky" />
            <StatCard label="Indexed Pages" value={String(stats.indexed_pages_total)} icon={Layers} accent="emerald" />
            <StatCard label="Embeddings" value={String(stats.embeddings_total)} icon={Database} accent="amber" />
            <StatCard label="Analyses Run" value={String(stats.analyses_total)} icon={Sparkles} accent="indigo" />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <StatCard
              label="Avg Query Latency"
              value={formatDuration(stats.avg_query_latency_ms)}
              icon={Gauge}
              accent="sky"
            />
            <StatCard
              label="Cache Hit Rate"
              value={formatPercent(stats.cache_hit_rate, 0)}
              icon={Zap}
              hint={`${stats.cache_hits} hits / ${stats.cache_misses} misses`}
              accent="emerald"
            />
            <StatCard
              label="Processing Now"
              value={String(
                (stats.documents_by_status.parsing ?? 0) +
                  (stats.documents_by_status.chunking ?? 0) +
                  (stats.documents_by_status.embedding ?? 0),
              )}
              icon={BarChart3}
              hint="documents mid-pipeline"
              accent="amber"
            />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle>Documents by processing status</CardTitle>
              </CardHeader>
              <CardContent className="h-64 pt-0">
                {statusChartData.length === 0 ? (
                  <EmptyChart label="No documents uploaded yet" />
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={statusChartData} layout="vertical" margin={{ left: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" horizontal={false} />
                      <XAxis type="number" allowDecimals={false} stroke="#8b94a7" fontSize={12} />
                      <YAxis
                        type="category"
                        dataKey="status"
                        stroke="#8b94a7"
                        fontSize={12}
                        width={80}
                      />
                      <Tooltip
                        contentStyle={{
                          background: "#111827",
                          border: "1px solid #1f2937",
                          borderRadius: 8,
                          fontSize: 12,
                        }}
                      />
                      <Bar dataKey="count" fill="#6366f1" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>AI Market Intelligence</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 pt-0">
                {!metricsQuery.data || metricsQuery.data.length === 0 ? (
                  <p className="text-xs text-muted">
                    No financial data points extracted yet — upload documents and run a
                    research query to populate this feed.
                  </p>
                ) : (
                  metricsQuery.data.slice(0, 6).map((m) => (
                    <div key={m.id} className="flex items-center justify-between text-xs">
                      <span className="text-muted">
                        {titleCase(m.metric_name)}
                        {m.year ? ` (${m.year})` : ""}
                      </span>
                      <span className="font-medium text-foreground">
                        {m.value.toLocaleString()} {m.unit.replace("usd_", "").replace("usd", "$")}
                      </span>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Recent documents</CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                {stats.recent_documents.length === 0 ? (
                  <p className="text-xs text-muted">No documents yet.</p>
                ) : (
                  <Table>
                    <Thead>
                      <Tr>
                        <Th>Document</Th>
                        <Th>Status</Th>
                        <Th>Uploaded</Th>
                      </Tr>
                    </Thead>
                    <Tbody>
                      {stats.recent_documents.map((d) => (
                        <Tr key={d.id}>
                          <Td className="max-w-[220px] truncate">{d.original_filename}</Td>
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

            <Card>
              <CardHeader>
                <CardTitle>Recent research queries</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 pt-0">
                {stats.recent_analysis_queries.length === 0 ? (
                  <p className="text-xs text-muted">
                    No analyses yet —{" "}
                    <Link href="/research" className="text-indigo-400 hover:underline">
                      ask a question
                    </Link>{" "}
                    to get started.
                  </p>
                ) : (
                  stats.recent_analysis_queries.map((q, i) => (
                    <div key={i} className="truncate rounded-md bg-white/[0.03] px-3 py-2 text-xs text-foreground">
                      {q}
                    </div>
                  ))
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

function EmptyChart({ label }: { label: string }) {
  return <div className="flex h-full items-center justify-center text-xs text-muted">{label}</div>;
}
