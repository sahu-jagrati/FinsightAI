import {
  Calculator,
  CheckCircle2,
  CircleDashed,
  FileSearch,
  GitCompareArrows,
  Loader2,
  Network,
  ScrollText,
  XCircle,
} from "lucide-react";
import { formatDuration } from "@/lib/utils";
import type { AgentStatusEvent } from "@/types/api";

const AGENT_ORDER = [
  "supervisor",
  "retrieval_agent",
  "financial_extraction_agent",
  "calculation_agent",
  "comparison_agent",
  "report_agent",
] as const;

const AGENT_META: Record<string, { label: string; icon: typeof Network }> = {
  supervisor: { label: "Supervisor", icon: Network },
  retrieval_agent: { label: "Retrieval Agent", icon: FileSearch },
  financial_extraction_agent: { label: "Financial Extraction Agent", icon: ScrollText },
  calculation_agent: { label: "Calculation Agent", icon: Calculator },
  comparison_agent: { label: "Comparison Agent", icon: GitCompareArrows },
  report_agent: { label: "Report Agent", icon: ScrollText },
};

type DisplayStatus = "waiting" | "running" | "completed" | "failed" | "skipped";

export function AgentTracePanel({
  events,
  streaming,
}: {
  events: AgentStatusEvent[];
  streaming: boolean;
}) {
  // Latest event per agent (an agent can appear twice: "running" then its
  // terminal status).
  const latestByAgent = new Map<string, AgentStatusEvent>();
  for (const e of events) latestByAgent.set(e.agent, e);

  const finished = !streaming && events.length > 0;

  const rows = AGENT_ORDER.map((agent) => {
    const event = latestByAgent.get(agent);
    let status: DisplayStatus = "waiting";
    if (event) status = event.status;
    else if (finished) status = "skipped";
    return { agent, event, status };
  });

  return (
    <div className="space-y-1">
      {rows.map(({ agent, event, status }, i) => {
        const meta = AGENT_META[agent];
        const Icon = meta.icon;
        return (
          <div key={agent} className="flex items-center gap-3 py-1.5">
            <div className="flex w-5 items-center justify-center">
              <StatusIcon status={status} />
            </div>
            <Icon className="h-3.5 w-3.5 shrink-0 text-muted" />
            <span
              className={`flex-1 text-xs ${
                status === "skipped" ? "text-muted/50 line-through" : "text-foreground"
              }`}
            >
              {meta.label}
            </span>
            {event?.execution_time_ms != null && (
              <span className="text-[11px] tabular-nums text-muted">
                {formatDuration(event.execution_time_ms)}
              </span>
            )}
            {i < AGENT_ORDER.length - 1 && (
              <span className="sr-only">then</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

function StatusIcon({ status }: { status: DisplayStatus }) {
  switch (status) {
    case "completed":
      return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />;
    case "running":
      return <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-400" />;
    case "failed":
      return <XCircle className="h-3.5 w-3.5 text-rose-400" />;
    case "skipped":
      return <div className="h-1.5 w-1.5 rounded-full bg-white/10" />;
    default:
      return <CircleDashed className="h-3.5 w-3.5 text-muted" />;
  }
}
