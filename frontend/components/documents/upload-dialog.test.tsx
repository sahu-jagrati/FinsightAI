import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { UploadDialog } from "./upload-dialog";
import * as apiClient from "@/lib/api-client";
import type { Document } from "@/types/api";

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof apiClient>("@/lib/api-client");
  return { ...actual, uploadDocument: vi.fn() };
});

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const FAKE_DOCUMENT: Document = {
  id: "doc-1",
  company: { id: "c-1", name: "Apple", ticker: "AAPL", industry: null, created_at: "2025-01-01" },
  original_filename: "apple_10k.pdf",
  document_type: "annual_report",
  reporting_period: "2025",
  source: null,
  status: "uploaded",
  status_detail: null,
  page_count: null,
  chunk_count: 0,
  file_size_bytes: 1024,
  processing_duration_ms: null,
  created_at: "2025-01-01",
  updated_at: "2025-01-01",
};

describe("UploadDialog", () => {
  beforeEach(() => {
    vi.mocked(apiClient.uploadDocument).mockReset();
  });

  it("renders nothing when closed", () => {
    renderWithClient(<UploadDialog open={false} onClose={vi.fn()} />);
    expect(screen.queryByText("Upload document")).not.toBeInTheDocument();
  });

  it("disables submit until a file is chosen", () => {
    renderWithClient(<UploadDialog open={true} onClose={vi.fn()} />);
    expect(screen.getByRole("button", { name: /upload$/i })).toBeDisabled();
  });

  it("submits the file, company, and document type on upload", async () => {
    vi.mocked(apiClient.uploadDocument).mockResolvedValue(FAKE_DOCUMENT);
    const onClose = vi.fn();
    const user = userEvent.setup();
    renderWithClient(<UploadDialog open={true} onClose={onClose} />);

    const file = new File(["revenue data"], "apple_10k.pdf", { type: "application/pdf" });
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(fileInput, file);

    await user.type(screen.getByPlaceholderText("e.g. Apple"), "Apple");
    await user.click(screen.getByRole("button", { name: /upload$/i }));

    expect(apiClient.uploadDocument).toHaveBeenCalledWith(
      expect.objectContaining({ companyName: "Apple", documentType: "annual_report" }),
    );
  });

  it("shows an error message when the upload fails", async () => {
    vi.mocked(apiClient.uploadDocument).mockRejectedValue(
      new apiClient.ApiError(400, "unsupported_file_type", "'.exe' is not a supported file type."),
    );
    // `accept` is a picker hint, not an enforcement mechanism (drag-and-drop
    // bypasses it in real browsers too) — the server is what actually
    // rejects unsupported types, which is exactly what this test verifies,
    // so this instance opts out of user-event's default accept filtering.
    const user = userEvent.setup({ applyAccept: false });
    renderWithClient(<UploadDialog open={true} onClose={vi.fn()} />);

    const file = new File(["x"], "malware.exe");
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(fileInput, file);
    await user.click(screen.getByRole("button", { name: /upload$/i }));

    expect(await screen.findByText(/not a supported file type/i)).toBeInTheDocument();
  });
});
