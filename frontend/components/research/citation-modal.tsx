"use client";

import { FileText } from "lucide-react";
import * as React from "react";
import Link from "next/link";
import type { Citation } from "@/types/api";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";

/**
 * Section 24's document viewer, scoped down: this shows the exact
 * document/page/company a citation points to (real, structured data from
 * the backend — see `Citation` in `app/agents/state.py`) rather than
 * rendering the source PDF inline. Full PDF.js-style page rendering with
 * highlighted spans is a natural next step (tracked in docs/PHASES.md)
 * that needs the backend to also store per-chunk bounding boxes, which
 * today's text-only extraction doesn't capture.
 */
export function CitationChip({ citation, index }: { citation: Citation; index: number }) {
  const [open, setOpen] = React.useState(false);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 rounded-full border border-border bg-white/[0.03] px-2.5 py-1 text-[11px] text-muted transition-colors hover:border-indigo-500/40 hover:text-foreground"
      >
        <span className="flex h-3.5 w-3.5 items-center justify-center rounded-full bg-indigo-500/20 text-[9px] font-semibold text-indigo-300">
          {index}
        </span>
        {citation.label}
      </button>

      <Modal open={open} onClose={() => setOpen(false)} title="Source">
        <div className="space-y-3 text-sm">
          <div className="flex items-center gap-2 text-foreground">
            <FileText className="h-4 w-4 text-indigo-400" />
            {citation.document_filename ?? "Unknown document"}
          </div>
          <dl className="grid grid-cols-2 gap-y-2 text-xs">
            <dt className="text-muted">Company</dt>
            <dd className="text-foreground">{citation.company ?? "—"}</dd>
            <dt className="text-muted">Page</dt>
            <dd className="text-foreground">{citation.page_number ?? "—"}</dd>
          </dl>
          <p className="text-xs text-muted">
            Open the source document in the document library to review the full page in context.
          </p>
          <Link href="/documents">
            <Button variant="secondary" size="sm" className="w-full">
              Open in Documents
            </Button>
          </Link>
        </div>
      </Modal>
    </>
  );
}
