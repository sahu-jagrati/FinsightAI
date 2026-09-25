"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import * as React from "react";
import { ApiError, getAnalysis, streamQuery } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import type { AgentStatusEvent, ReportResult } from "@/types/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { AgentTracePanel } from "@/components/research/agent-trace-panel";
import { RecentResearchPanel } from "@/components/research/recent-research";
import { ReportView } from "@/components/research/report-view";

const EXAMPLE_QUERIES = [
  "Compare Apple's and Microsoft's revenue growth from 2022 to 2025.",
  "Calculate Microsoft's 3-year revenue CAGR.",
  "Summarize the major risks mentioned in the latest annual report.",
];

interface Turn {
  id: string;
  /** The persisted analysis id once known — set immediately when reopening
   * a saved item, or once the "final" SSE frame lands for a live query. */
  analysisId: string | null;
  /** True when this turn was reopened from Recent Research rather than
   * just having been run live — no agent trace to show for it. */
  fromHistory: boolean;
  query: string;
  events: AgentStatusEvent[];
  report: ReportResult | null;
  streaming: boolean;
  error: string | null;
}

export default function ResearchPage() {
  const [input, setInput] = React.useState("");
  const [turns, setTurns] = React.useState<Turn[]>([]);
  const [historyRefresh, setHistoryRefresh] = React.useState(0);
  const [activeTurnId, setActiveTurnId] = React.useState<string | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const queryClient = useQueryClient();

  async function runQuery(query: string) {
    const id = crypto.randomUUID();
    setTurns((prev) => [
      ...prev,
      {
        id,
        analysisId: null,
        fromHistory: false,
        query,
        events: [],
        report: null,
        streaming: true,
        error: null,
      },
    ]);
    setActiveTurnId(id);
    setInput("");

    function update(patch: Partial<Turn>) {
      setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, ...patch } : t)));
    }

    try {
      for await (const event of streamQuery(query)) {
        if (event.event === "agent_status") {
          setTurns((prev) =>
            prev.map((t) => (t.id === id ? { ...t, events: [...t.events, event] } : t)),
          );
        } else if (event.event === "final") {
          update({ report: event.report, streaming: false, analysisId: event.analysis_id });
          queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] });
          queryClient.invalidateQueries({ queryKey: ["metrics"] });
          // Refreshes the Recent Research sidebar so the query that just
          // completed shows up without a manual reload.
          setHistoryRefresh((n) => n + 1);
        }
      }
    } catch (err) {
      update({
        streaming: false,
        error: err instanceof ApiError ? err.message : "The research query failed. Please try again.",
      });
    }
  }

  /**
   * Reopens a previously persisted analysis. This reads the already-saved
   * `result` from `GET /api/analyses/{id}` — it never calls `streamQuery`
   * or `/api/analyze`, so no LLM/agent work happens.
   */
  async function loadAnalysis(analysisId: string) {
    setLoadError(null);
    const existing = turns.find((t) => t.analysisId === analysisId);
    if (existing) {
      setActiveTurnId(existing.id);
      return;
    }

    const id = crypto.randomUUID();
    setTurns((prev) => [
      ...prev,
      {
        id,
        analysisId,
        fromHistory: true,
        query: "",
        events: [],
        report: null,
        streaming: true,
        error: null,
      },
    ]);
    setActiveTurnId(id);

    try {
      const analysis = await getAnalysis(analysisId);
      setTurns((prev) =>
        prev.map((t) =>
          t.id === id
            ? {
                ...t,
                query: analysis.query,
                report: analysis.result,
                error: analysis.error,
                streaming: false,
              }
            : t,
        ),
      );
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Could not load this research item.";
      setTurns((prev) => prev.filter((t) => t.id !== id));
      setActiveTurnId(null);
      setLoadError(message);
    }
  }

  return (
    <div className="mx-auto flex h-full max-w-6xl flex-col p-6">
      <div className="mb-4">
        <h1 className="flex items-center gap-2 text-xl font-semibold text-foreground">
          <Sparkles className="h-5 w-5 text-indigo-400" />
          Research
        </h1>
        <p className="text-sm text-muted">
          Ask complex financial questions across your indexed documents.
        </p>
      </div>

      <div className="grid flex-1 grid-cols-1 gap-6 overflow-hidden md:grid-cols-[240px_1fr]">
        <aside className="hidden overflow-y-auto border-r border-border pr-4 md:block">
          <RecentResearchPanel
            activeAnalysisId={turns.find((t) => t.id === activeTurnId)?.analysisId}
            onSelect={loadAnalysis}
            refreshToken={historyRefresh}
          />
        </aside>

        <div className="flex flex-col overflow-hidden">
          <div className="flex-1 space-y-6 overflow-y-auto pb-4">
            {loadError && (
              <p className="rounded-lg border border-rose-500/30 bg-rose-500/5 px-3 py-2 text-sm text-rose-400">
                {loadError}
              </p>
            )}

            {turns.length === 0 && (
              <Card>
                <CardContent className="space-y-3 p-6">
                  <p className="text-sm text-muted">Try one of these:</p>
                  <div className="flex flex-wrap gap-2">
                    {EXAMPLE_QUERIES.map((q) => (
                      <button
                        key={q}
                        onClick={() => runQuery(q)}
                        className="rounded-full border border-border bg-white/[0.03] px-3 py-1.5 text-xs text-muted transition-colors hover:border-indigo-500/40 hover:text-foreground"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {turns.map((turn) => (
              <div
                key={turn.id}
                id={`turn-${turn.id}`}
                className="space-y-3"
                onClick={() => setActiveTurnId(turn.id)}
              >
                <div className="flex items-center justify-end gap-2">
                  {turn.fromHistory && (
                    <span className="text-[11px] font-medium uppercase tracking-wide text-muted">
                      From history
                    </span>
                  )}
                  <div className="ml-auto max-w-2xl rounded-xl bg-indigo-600/15 px-4 py-2.5 text-sm text-indigo-100">
                    {turn.query || (turn.streaming ? "Loading…" : "")}
                  </div>
                </div>

                <Card>
                  <CardContent
                    className={cn(
                      "grid grid-cols-1 gap-5 p-5",
                      !turn.fromHistory && "md:grid-cols-[220px_1fr]",
                    )}
                  >
                    {!turn.fromHistory && (
                      <div className="border-b border-border pb-4 md:border-b-0 md:border-r md:pb-0 md:pr-5">
                        <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">
                          Agent trace
                        </div>
                        <AgentTracePanel events={turn.events} streaming={turn.streaming} />
                      </div>
                    )}

                    <div>
                      {turn.error && <p className="text-sm text-rose-400">{turn.error}</p>}
                      {turn.report && <ReportView report={turn.report} />}
                      {turn.streaming && !turn.report && (
                        <p className="text-sm text-muted">
                          {turn.fromHistory ? "Loading saved research…" : "Researching…"}
                        </p>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </div>
            ))}
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (input.trim()) runQuery(input.trim());
            }}
            className="flex items-center gap-2 border-t border-border pt-4"
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about revenue, growth, margins, comparisons…"
              className="h-11 flex-1 rounded-lg border border-border bg-surface-raised px-4 text-sm text-foreground placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <Button type="submit" size="lg" disabled={!input.trim()}>
              Ask
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
