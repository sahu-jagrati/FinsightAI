"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Search, Trash2 } from "lucide-react";
import * as React from "react";
import { deleteDocument, listDocuments } from "@/lib/api-client";
import { formatDate, formatDuration, titleCase } from "@/lib/utils";
import type { Document, DocumentType } from "@/types/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/table";
import { DocumentStatusBadge, DocumentStatusPipeline } from "@/components/documents/status-badge";
import { UploadDialog } from "@/components/documents/upload-dialog";

const DOCUMENT_TYPES: DocumentType[] = [
  "annual_report",
  "quarterly_report",
  "sec_filing",
  "earnings_report",
  "news",
  "other",
];

const ACTIVE_STATUSES = new Set(["uploaded", "parsing", "chunking", "embedding"]);

export default function DocumentsPage() {
  const [search, setSearch] = React.useState("");
  const [typeFilter, setTypeFilter] = React.useState<DocumentType | "">("");
  const [uploadOpen, setUploadOpen] = React.useState(false);
  const [selected, setSelected] = React.useState<Document | null>(null);
  const queryClient = useQueryClient();

  const documentsQuery = useQuery({
    queryKey: ["documents", search, typeFilter],
    queryFn: () =>
      listDocuments({
        search: search || undefined,
        document_type: typeFilter || undefined,
        limit: 50,
      }),
    // Poll while anything is still mid-pipeline so status pills update live
    // without the user refreshing (Section 4/21).
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      return items.some((d) => ACTIVE_STATUSES.has(d.status)) ? 3000 : false;
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteDocument,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] });
      setSelected(null);
    },
  });

  const documents = documentsQuery.data?.items ?? [];

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Documents</h1>
          <p className="text-sm text-muted">
            Upload annual reports, filings, and earnings releases for indexing.
          </p>
        </div>
        <Button onClick={() => setUploadOpen(true)}>
          <Plus className="h-4 w-4" />
          Upload document
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative w-64">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
          <Input
            placeholder="Search filename…"
            className="pl-8"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value as DocumentType | "")}>
          <option value="">All types</option>
          {DOCUMENT_TYPES.map((t) => (
            <option key={t} value={t}>
              {titleCase(t)}
            </option>
          ))}
        </Select>
      </div>

      <Card>
        <CardContent className="p-0">
          {documentsQuery.isLoading ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-10" />
              ))}
            </div>
          ) : documents.length === 0 ? (
            <div className="p-10 text-center text-sm text-muted">
              No documents match your filters yet.
            </div>
          ) : (
            <Table>
              <Thead>
                <Tr>
                  <Th>Document</Th>
                  <Th>Company</Th>
                  <Th>Type</Th>
                  <Th>Period</Th>
                  <Th>Pipeline</Th>
                  <Th>Chunks</Th>
                  <Th>Uploaded</Th>
                  <Th />
                </Tr>
              </Thead>
              <Tbody>
                {documents.map((d) => (
                  <Tr key={d.id} className="cursor-pointer" onClick={() => setSelected(d)}>
                    <Td className="max-w-[240px] truncate font-medium">{d.original_filename}</Td>
                    <Td className="text-muted">{d.company?.name ?? "—"}</Td>
                    <Td className="text-muted">{titleCase(d.document_type)}</Td>
                    <Td className="text-muted">{d.reporting_period ?? "—"}</Td>
                    <Td>
                      {d.status === "failed" ? (
                        <DocumentStatusBadge status={d.status} />
                      ) : (
                        <DocumentStatusPipeline status={d.status} />
                      )}
                    </Td>
                    <Td className="text-muted">{d.chunk_count}</Td>
                    <Td className="text-muted">{formatDate(d.created_at)}</Td>
                    <Td>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          if (confirm(`Delete "${d.original_filename}"?`)) {
                            deleteMutation.mutate(d.id);
                          }
                        }}
                        className="rounded-md p-1.5 text-muted hover:bg-rose-500/10 hover:text-rose-400"
                        aria-label="Delete document"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          )}
        </CardContent>
      </Card>

      <UploadDialog open={uploadOpen} onClose={() => setUploadOpen(false)} />

      <Modal
        open={!!selected}
        onClose={() => setSelected(null)}
        title={selected?.original_filename ?? ""}
      >
        {selected && (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            <DetailRow label="Status">
              <DocumentStatusBadge status={selected.status} />
            </DetailRow>
            <DetailRow label="Company">{selected.company?.name ?? "—"}</DetailRow>
            <DetailRow label="Type">{titleCase(selected.document_type)}</DetailRow>
            <DetailRow label="Reporting period">{selected.reporting_period ?? "—"}</DetailRow>
            <DetailRow label="Pages">{selected.page_count ?? "—"}</DetailRow>
            <DetailRow label="Chunks indexed">{selected.chunk_count}</DetailRow>
            <DetailRow label="Processing time">
              {formatDuration(selected.processing_duration_ms)}
            </DetailRow>
            <DetailRow label="File size">
              {selected.file_size_bytes
                ? `${(selected.file_size_bytes / 1024).toFixed(0)} KB`
                : "—"}
            </DetailRow>
            {selected.status_detail && (
              <div className="col-span-2">
                <dt className="text-xs text-muted">Detail</dt>
                <dd className="mt-0.5 text-xs text-rose-400">{selected.status_detail}</dd>
              </div>
            )}
          </dl>
        )}
      </Modal>
    </div>
  );
}

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-0.5 text-foreground">{children}</dd>
    </div>
  );
}
