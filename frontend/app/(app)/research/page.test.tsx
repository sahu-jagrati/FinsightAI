import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ResearchPage from "./page";
import * as apiClient from "@/lib/api-client";
import type { QueryStreamEvent, ReportResult } from "@/types/api";

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof apiClient>("@/lib/api-client");
  return { ...actual, streamQuery: vi.fn() };
});

const REPORT: ReportResult = {
  executive_summary: "Apple's revenue grew from $100B to $150B.",
  key_findings: ["Revenue CAGR: 14.5%"],
  comparison_table: [],
  calculations: [],
  sources: ["Apple — apple_10k.pdf, p. 25"],
  citations: [
    {
      label: "Apple — apple_10k.pdf, p. 25",
      company: "Apple",
      document_id: "doc-1",
      document_filename: "apple_10k.pdf",
      page_number: 25,
    },
  ],
  confidence: 0.87,
  insufficient_evidence: false,
};

async function* fakeStream(): AsyncGenerator<QueryStreamEvent> {
  yield { event: "agent_status", agent: "supervisor", status: "running", execution_time_ms: null, error: null };
  yield {
    event: "agent_status",
    agent: "retrieval_agent",
    status: "completed",
    execution_time_ms: 80,
    error: null,
  };
  yield { event: "final", analysis_id: "analysis-1", report: REPORT };
}

function renderWithClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ResearchPage />
    </QueryClientProvider>,
  );
}

describe("ResearchPage", () => {
  it("streams agent progress and renders the final grounded report", async () => {
    vi.mocked(apiClient.streamQuery).mockReturnValue(fakeStream());
    const user = userEvent.setup();
    renderWithClient();

    const input = screen.getByPlaceholderText(/ask about revenue/i);
    await user.type(input, "What was Apple's revenue growth?");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByText(/Apple's revenue grew/)).toBeInTheDocument();
    expect(screen.getByText("Revenue CAGR: 14.5%")).toBeInTheDocument();
    expect(screen.getByText(/Apple — apple_10k.pdf, p. 25/)).toBeInTheDocument();
    // the user's own question is echoed back as a chat bubble
    expect(screen.getByText("What was Apple's revenue growth?")).toBeInTheDocument();
  });

  it("clicking an example query runs it directly", async () => {
    vi.mocked(apiClient.streamQuery).mockReturnValue(fakeStream());
    const user = userEvent.setup();
    renderWithClient();

    await user.click(
      screen.getByText("Calculate Microsoft's 3-year revenue CAGR."),
    );

    expect(await screen.findByText(/Apple's revenue grew/)).toBeInTheDocument();
  });
});
