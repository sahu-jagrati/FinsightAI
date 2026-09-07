import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DocumentStatusBadge, DocumentStatusPipeline } from "./status-badge";

describe("DocumentStatusBadge", () => {
  it("renders a human label for each status", () => {
    render(<DocumentStatusBadge status="indexed" />);
    expect(screen.getByText("Indexed")).toBeInTheDocument();
  });

  it("renders the failed status distinctly", () => {
    render(<DocumentStatusBadge status="failed" />);
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });
});

describe("DocumentStatusPipeline", () => {
  it("renders one segment per pipeline stage", () => {
    const { container } = render(<DocumentStatusPipeline status="chunking" />);
    expect(container.querySelectorAll("div[title]")).toHaveLength(5);
  });

  it("falls back to a badge when the document failed", () => {
    render(<DocumentStatusPipeline status="failed" />);
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });
});
