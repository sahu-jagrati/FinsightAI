import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AgentTracePanel } from "./agent-trace-panel";
import type { AgentStatusEvent } from "@/types/api";

describe("AgentTracePanel", () => {
  it("shows every agent as waiting before any events arrive", () => {
    render(<AgentTracePanel events={[]} streaming={true} />);
    expect(screen.getByText("Supervisor")).toBeInTheDocument();
    expect(screen.getByText("Report Agent")).toBeInTheDocument();
  });

  it("reflects the latest status per agent while streaming", () => {
    const events: AgentStatusEvent[] = [
      { event: "agent_status", agent: "supervisor", status: "running", execution_time_ms: null, error: null },
      { event: "agent_status", agent: "retrieval_agent", status: "completed", execution_time_ms: 120, error: null },
    ];
    render(<AgentTracePanel events={events} streaming={true} />);
    expect(screen.getByText("120ms")).toBeInTheDocument();
  });

  it("marks agents the supervisor never ran as skipped once streaming finishes", () => {
    const events: AgentStatusEvent[] = [
      { event: "agent_status", agent: "supervisor", status: "running", execution_time_ms: null, error: null },
      { event: "agent_status", agent: "retrieval_agent", status: "completed", execution_time_ms: 100, error: null },
      { event: "agent_status", agent: "report_agent", status: "completed", execution_time_ms: 50, error: null },
      { event: "agent_status", agent: "supervisor", status: "completed", execution_time_ms: 200, error: null },
    ];
    render(<AgentTracePanel events={events} streaming={false} />);
    // calculation_agent and comparison_agent never appeared -> skipped (struck through)
    expect(screen.getByText("Calculation Agent")).toHaveClass("line-through");
    expect(screen.getByText("Retrieval Agent")).not.toHaveClass("line-through");
  });
});
