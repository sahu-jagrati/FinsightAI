"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import * as React from "react";
import { ApiError, uploadDocument } from "@/lib/api-client";
import type { DocumentType } from "@/types/api";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";

const DOCUMENT_TYPES: { value: DocumentType; label: string }[] = [
  { value: "annual_report", label: "Annual Report" },
  { value: "quarterly_report", label: "Quarterly Report" },
  { value: "sec_filing", label: "SEC Filing" },
  { value: "earnings_report", label: "Earnings Report" },
  { value: "news", label: "News" },
  { value: "other", label: "Other" },
];

export function UploadDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [file, setFile] = React.useState<File | null>(null);
  const [companyName, setCompanyName] = React.useState("");
  const [documentType, setDocumentType] = React.useState<DocumentType>("annual_report");
  const [reportingPeriod, setReportingPeriod] = React.useState("");

  const mutation = useMutation({
    mutationFn: () => {
      if (!file) throw new Error("Choose a file first.");
      return uploadDocument({
        file,
        companyName: companyName || undefined,
        documentType,
        reportingPeriod: reportingPeriod || undefined,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] });
      setFile(null);
      setCompanyName("");
      setReportingPeriod("");
      onClose();
    },
  });

  return (
    <Modal open={open} onClose={onClose} title="Upload document">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate();
        }}
      >
        <div>
          <label className="mb-1.5 block text-xs font-medium text-muted">File</label>
          <input
            type="file"
            accept=".pdf,.txt,.html,.md"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="block w-full text-sm text-muted file:mr-3 file:rounded-md file:border-0 file:bg-indigo-600 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-white hover:file:bg-indigo-500"
          />
          <p className="mt-1 text-[11px] text-muted">PDF, TXT, HTML, or Markdown.</p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted">Company</label>
            <Input
              placeholder="e.g. Apple"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted">Reporting period</label>
            <Input
              placeholder="e.g. 2025 or Q4 2025"
              value={reportingPeriod}
              onChange={(e) => setReportingPeriod(e.target.value)}
            />
          </div>
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-medium text-muted">Document type</label>
          <Select
            className="w-full"
            value={documentType}
            onChange={(e) => setDocumentType(e.target.value as DocumentType)}
          >
            {DOCUMENT_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </Select>
        </div>

        {mutation.isError && (
          <p className="text-xs text-rose-400">
            {mutation.error instanceof ApiError
              ? mutation.error.message
              : "Upload failed. Please try again."}
          </p>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={!file || mutation.isPending}>
            <Upload className="h-3.5 w-3.5" />
            {mutation.isPending ? "Uploading…" : "Upload"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
