"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, History, Search, Trash2 } from "lucide-react";
import * as React from "react";
import { deleteAnalysis, listAnalyses } from "@/lib/api-client";
import { cn, formatDateTime, formatPercent } from "@/lib/utils";
import type { AnalysisSummary } from "@/types/api";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";

const SIDEBAR_LIMIT = 6;
const ALL_LIMIT = 50;

/**
 * "Recent Research" (Research History): lists analyses already persisted
 * by the backend (Section 20) and lets the user reopen one without
 * re-running the agent pipeline — selecting an item hands the caller the
 * analysis id, and the caller loads its already-computed `result` via
 * `getAnalysis`, never `streamQuery`/`/api/analyze`.
 */
export function RecentResearchPanel({
  activeAnalysisId,
  onSelect,
  refreshToken,
}: {
  activeAnalysisId?: string | null;
  onSelect: (id: string) => void;
  /** Bump this after a new query completes so the list picks it up. */
  refreshToken?: number;
}) {
  const [viewAllOpen, setViewAllOpen] = React.useState(false);

  const sidebarQuery = useQuery({
    queryKey: ["analyses", "sidebar", refreshToken],
    queryFn: () => listAnalyses({ limit: SIDEBAR_LIMIT }),
  });

  const items = sidebarQuery.data?.items ?? [];
  const total = sidebarQuery.data?.total ?? 0;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted">
          <History className="h-3.5 w-3.5" />
          Recent research
        </div>
        {total > SIDEBAR_LIMIT && (
          <button
            onClick={() => setViewAllOpen(true)}
            className="text-xs font-medium text-indigo-400 hover:text-indigo-300"
          >
            View all
          </button>
        )}
      </div>

      {sidebarQuery.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-14" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <p className="text-xs text-muted">
          Your past research queries will show up here once you ask one.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {items.map((item) => (
            <RecentResearchItem
              key={item.id}
              item={item}
              active={item.id === activeAnalysisId}
              onSelect={() => onSelect(item.id)}
            />
          ))}
        </ul>
      )}

      <RecentResearchAllModal
        open={viewAllOpen}
        onClose={() => setViewAllOpen(false)}
        activeAnalysisId={activeAnalysisId}
        onSelect={(id) => {
          onSelect(id);
          setViewAllOpen(false);
        }}
      />
    </div>
  );
}

function RecentResearchItem({
  item,
  active,
  onSelect,
  onDeleted,
}: {
  item: AnalysisSummary;
  active: boolean;
  onSelect: () => void;
  onDeleted?: () => void;
}) {
  const queryClient = useQueryClient();
  const deleteMutation = useMutation({
    mutationFn: () => deleteAnalysis(item.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["analyses"] });
      onDeleted?.();
    },
  });

  return (
    <li>
      <button
        onClick={onSelect}
        className={cn(
          "group flex w-full flex-col gap-1 rounded-lg border px-3 py-2 text-left transition-colors",
          active
            ? "border-indigo-500/40 bg-indigo-600/10"
            : "border-border bg-white/[0.02] hover:border-indigo-500/30 hover:bg-white/[0.04]",
        )}
      >
        <div className="flex items-start justify-between gap-2">
          <span className="line-clamp-2 text-xs font-medium text-foreground">{item.title}</span>
          <button
            onClick={(e) => {
              e.stopPropagation();
              if (confirm(`Delete "${item.title}"?`)) deleteMutation.mutate();
            }}
            className="shrink-0 rounded-md p-1 text-muted opacity-0 hover:bg-rose-500/10 hover:text-rose-400 group-hover:opacity-100"
            aria-label="Delete research item"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-muted">
          <span>{formatDateTime(item.created_at)}</span>
          {item.insufficient_evidence ? (
            <span className="flex items-center gap-1 text-amber-400">
              <AlertTriangle className="h-3 w-3" />
              No answer
            </span>
          ) : (
            item.confidence != null && <span>{formatPercent(item.confidence, 0)} confidence</span>
          )}
        </div>
      </button>
    </li>
  );
}

function RecentResearchAllModal({
  open,
  onClose,
  activeAnalysisId,
  onSelect,
}: {
  open: boolean;
  onClose: () => void;
  activeAnalysisId?: string | null;
  onSelect: (id: string) => void;
}) {
  const [search, setSearch] = React.useState("");

  const allQuery = useQuery({
    queryKey: ["analyses", "all", search],
    queryFn: () => listAnalyses({ limit: ALL_LIMIT, search: search || undefined }),
    enabled: open,
  });

  const items = allQuery.data?.items ?? [];

  return (
    <Modal open={open} onClose={onClose} title="All research" className="max-w-xl">
      <div className="space-y-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
          <Input
            placeholder="Search past research…"
            className="pl-8"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            autoFocus
          />
        </div>

        <div className="max-h-96 space-y-1.5 overflow-y-auto">
          {allQuery.isLoading ? (
            Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-14" />)
          ) : items.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted">No research matches your search.</p>
          ) : (
            items.map((item) => (
              <RecentResearchItem
                key={item.id}
                item={item}
                active={item.id === activeAnalysisId}
                onSelect={() => onSelect(item.id)}
              />
            ))
          )}
        </div>
      </div>
    </Modal>
  );
}
