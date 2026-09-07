"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertOctagon, CheckCircle2, XCircle } from "lucide-react";
import { getDashboardStats } from "@/lib/api-client";
import { API_BASE_URL } from "@/lib/config";
import { formatDuration, formatPercent } from "@/lib/utils";
import type { HealthResponse } from "@/types/health";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE_URL}/api/health`, { cache: "no-store" });
  return res.json();
}

export default function AdminPage() {
  const healthQuery = useQuery({
    queryKey: ["system-health"],
    queryFn: fetchHealth,
    refetchInterval: 15_000,
  });
  const statsQuery = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: getDashboardStats,
    refetchInterval: 15_000,
  });

  const stats = statsQuery.data;

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">System Monitoring</h1>
        <p className="text-sm text-muted">
          Live infrastructure health and indexing/query performance.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Infrastructure</CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          {healthQuery.isLoading ? (
            <Skeleton className="h-16" />
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              {healthQuery.data?.components.map((c) => (
                <div
                  key={c.name}
                  className="flex items-center gap-2.5 rounded-lg border border-border bg-white/[0.02] px-3 py-2.5"
                >
                  {c.status === "ok" ? (
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
                  ) : (
                    <XCircle className="h-4 w-4 shrink-0 text-rose-400" />
                  )}
                  <div className="min-w-0">
                    <div className="text-sm font-medium capitalize text-foreground">
                      {c.name}
                    </div>
                    {c.detail && <div className="truncate text-[11px] text-muted">{c.detail}</div>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {stats && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Metric label="Indexed documents" value={String(stats.documents_total)} />
          <Metric label="Embeddings stored" value={String(stats.embeddings_total)} />
          <Metric label="Cache hit ratio" value={formatPercent(stats.cache_hit_rate, 0)} />
          <Metric label="Avg query latency" value={formatDuration(stats.avg_query_latency_ms)} />
          <Metric label="Analyses run" value={String(stats.analyses_total)} />
          <Metric
            label="Failed documents"
            value={String(stats.documents_by_status.failed ?? 0)}
            danger={(stats.documents_by_status.failed ?? 0) > 0}
          />
        </div>
      )}

      {stats && (stats.documents_by_status.failed ?? 0) > 0 && (
        <div className="flex items-center gap-2 rounded-lg border border-rose-500/30 bg-rose-500/5 px-4 py-3 text-sm text-rose-300">
          <AlertOctagon className="h-4 w-4 shrink-0" />
          {stats.documents_by_status.failed} document(s) failed processing — check the Documents
          page for details.
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, danger }: { label: string; value: string; danger?: boolean }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-xs text-muted">{label}</div>
        <div className={`mt-1 text-xl font-semibold ${danger ? "text-rose-400" : "text-foreground"}`}>
          {value}
        </div>
      </CardContent>
    </Card>
  );
}
