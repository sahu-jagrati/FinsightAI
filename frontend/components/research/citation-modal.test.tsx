import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { CitationChip } from "./citation-modal";
import type { Citation } from "@/types/api";

const citation: Citation = {
  label: "Apple — apple_10k.pdf, p. 25",
  company: "Apple",
  document_id: "doc-1",
  document_filename: "apple_10k.pdf",
  page_number: 25,
};

describe("CitationChip", () => {
  it("renders the citation label collapsed by default", () => {
    render(<CitationChip citation={citation} index={1} />);
    expect(screen.getByText(citation.label)).toBeInTheDocument();
    expect(screen.queryByText("apple_10k.pdf", { selector: "div" })).not.toBeInTheDocument();
  });

  it("opens a detail modal with document/page/company on click", async () => {
    const user = userEvent.setup();
    render(<CitationChip citation={citation} index={1} />);

    await user.click(screen.getByRole("button"));

    expect(screen.getByText("Source")).toBeInTheDocument();
    expect(screen.getByText("25")).toBeInTheDocument();
    expect(screen.getAllByText("Apple").length).toBeGreaterThan(0);
  });
});
