"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import * as React from "react";
import { ApiError, streamQuery } from "@/lib/api-client";
import type { AgentStatusEvent, ReportResult } from "@/types/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { AgentTracePanel } from "@/components/research/agent-trace-panel";
import { ReportView } from "@/components/research/report-view";

const EXAMPLE_QUERIES = [
  "Compare Apple's and Microsoft's revenue growth from 2022 to 2025.",
  "Calculate Microsoft's 3-year revenue CAGR.",
  "Summarize the major risks mentioned in the latest annual report.",
];

interface Turn {
  id: string;
  query: string;
  events: AgentStatusEvent[];
  report: ReportResult | null;
  streaming: boolean;
  error: string | null;
}

export default function ResearchPage() {
  const [input, setInput] = React.useState("");
  const [turns, setTurns] = React.useState<Turn[]>([]);
  const queryClient = useQueryClient();

  async function runQuery(query: string) {
    const id = crypto.randomUUID();
    setTurns((prev) => [
      ...prev,
      { id, query, events: [], report: null, streaming: true, error: null },
    ]);
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
          update({ report: event.report, streaming: false });
          queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] });
          queryClient.invalidateQueries({ queryKey: ["metrics"] });
        }
      }
    } catch (err) {
      update({
        streaming: false,
        error: err instanceof ApiError ? err.message : "The research query failed. Please try again.",
      });
    }
  }

  return (
    <div className="mx-auto flex h-full max-w-5xl flex-col p-6">
      <div className="mb-4">
        <h1 className="flex items-center gap-2 text-xl font-semibold text-foreground">
          <Sparkles className="h-5 w-5 text-indigo-400" />
          Research
        </h1>
        <p className="text-sm text-muted">
          Ask complex financial questions across your indexed documents.
        </p>
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto pb-4">
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
          <div key={turn.id} className="space-y-3">
            <div className="ml-auto max-w-2xl rounded-xl bg-indigo-600/15 px-4 py-2.5 text-sm text-indigo-100">
              {turn.query}
            </div>

            <Card>
              <CardContent className="grid grid-cols-1 gap-5 p-5 md:grid-cols-[220px_1fr]">
                <div className="border-b border-border pb-4 md:border-b-0 md:border-r md:pb-0 md:pr-5">
                  <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">
                    Agent trace
                  </div>
                  <AgentTracePanel events={turn.events} streaming={turn.streaming} />
                </div>

                <div>
                  {turn.error && <p className="text-sm text-rose-400">{turn.error}</p>}
                  {turn.report && <ReportView report={turn.report} />}
                  {turn.streaming && !turn.report && (
                    <p className="text-sm text-muted">Researching…</p>
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
  );
}
