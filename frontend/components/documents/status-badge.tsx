import { Badge } from "@/components/ui/badge";
import type { DocumentStatus } from "@/types/api";

const STATUS_CONFIG: Record<DocumentStatus, { label: string; variant: "neutral" | "info" | "success" | "warning" | "danger" }> = {
  uploaded: { label: "Uploaded", variant: "neutral" },
  parsing: { label: "Parsing", variant: "info" },
  chunking: { label: "Chunking", variant: "info" },
  embedding: { label: "Embedding", variant: "warning" },
  indexed: { label: "Indexed", variant: "success" },
  failed: { label: "Failed", variant: "danger" },
};

export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.uploaded;
  return <Badge variant={config.variant}>{config.label}</Badge>;
}

const PIPELINE_STAGES: DocumentStatus[] = ["uploaded", "parsing", "chunking", "embedding", "indexed"];

/** Section 4: "Uploaded → Parsing → Chunking → Embedding → Indexed" as a
 * literal progress rail, not just a status word. */
export function DocumentStatusPipeline({ status }: { status: DocumentStatus }) {
  if (status === "failed") {
    return <DocumentStatusBadge status="failed" />;
  }
  const currentIndex = PIPELINE_STAGES.indexOf(status);

  return (
    <div className="flex items-center gap-1">
      {PIPELINE_STAGES.map((stage, i) => (
        <div
          key={stage}
          title={stage}
          className={`h-1.5 w-6 rounded-full ${
            i <= currentIndex ? "bg-indigo-500" : "bg-white/10"
          }`}
        />
      ))}
    </div>
  );
}
