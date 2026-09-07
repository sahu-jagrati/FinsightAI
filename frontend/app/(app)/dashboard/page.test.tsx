import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import DashboardPage from "./page";
import * as apiClient from "@/lib/api-client";
import type { DashboardStats } from "@/types/api";

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof apiClient>("@/lib/api-client");
  return { ...actual, getDashboardStats: vi.fn(), listMetrics: vi.fn() };
});

const STATS: DashboardStats = {
  documents_total: 4,
  companies_total: 2,
  indexed_pages_total: 120,
  embeddings_total: 340,
  analyses_total: 7,
  documents_by_status: { indexed: 3, parsing: 1 },
  avg_query_latency_ms: 842,
  cache_hit_rate: 0.63,
  cache_hits: 63,
  cache_misses: 37,
  recent_documents: [],
  recent_analysis_queries: ["What was Apple's revenue in 2025?"],
};

function renderWithClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DashboardPage />
    </QueryClientProvider>,
  );
}

describe("DashboardPage", () => {
  it("renders real stats from the API, not hardcoded numbers", async () => {
    vi.mocked(apiClient.getDashboardStats).mockResolvedValue(STATS);
    vi.mocked(apiClient.listMetrics).mockResolvedValue([]);

    renderWithClient();

    expect(await screen.findByText("4")).toBeInTheDocument(); // documents_total
    expect(screen.getByText("2")).toBeInTheDocument(); // companies_total
    expect(screen.getByText("7")).toBeInTheDocument(); // analyses_total
    expect(screen.getByText("What was Apple's revenue in 2025?")).toBeInTheDocument();
  });

  it("shows an error state when the backend is unreachable", async () => {
    vi.mocked(apiClient.getDashboardStats).mockRejectedValue(new Error("network error"));
    vi.mocked(apiClient.listMetrics).mockResolvedValue([]);

    renderWithClient();

    await waitFor(() =>
      expect(screen.getByText(/couldn.t load dashboard stats/i)).toBeInTheDocument(),
    );
  });
});
