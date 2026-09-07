// Mirrors backend/app/schemas/*.py — keep in sync as fields change.

export type DocumentType =
  | "annual_report"
  | "quarterly_report"
  | "sec_filing"
  | "earnings_report"
  | "news"
  | "other";

export type DocumentStatus =
  | "uploaded"
  | "parsing"
  | "chunking"
  | "embedding"
  | "indexed"
  | "failed";

export interface Company {
  id: string;
  name: string;
  ticker: string | null;
  industry: string | null;
  created_at: string;
}

export interface Document {
  id: string;
  company: Company | null;
  original_filename: string;
  document_type: DocumentType;
  reporting_period: string | null;
  source: string | null;
  status: DocumentStatus;
  status_detail: string | null;
  page_count: number | null;
  chunk_count: number;
  file_size_bytes: number | null;
  processing_duration_ms: number | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentListResponse {
  items: Document[];
  total: number;
  limit: number;
  offset: number;
}

export interface CalculationResult {
  operation: string;
  result: number;
  formula: string;
  inputs: Record<string, unknown>;
}

export interface ComparisonRow {
  company: string;
  metric: string;
  values_by_year: Record<string, number>;
  calculation: CalculationResult | null;
}

export interface Citation {
  label: string;
  company: string | null;
  document_id: string | null;
  document_filename: string | null;
  page_number: number | null;
}

export interface ReportResult {
  executive_summary: string;
  key_findings: string[];
  comparison_table: ComparisonRow[];
  calculations: CalculationResult[];
  sources: string[];
  citations: Citation[];
  confidence: number;
  insufficient_evidence: boolean;
}

export type AgentRunStatus = "waiting" | "running" | "completed" | "failed";
export type AnalysisStatus = "pending" | "running" | "completed" | "failed";

export interface AgentRun {
  id: string;
  agent_name: string;
  status: AgentRunStatus;
  step_order: number;
  input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  error: string | null;
  cache_hit: boolean;
  execution_time_ms: number | null;
  created_at: string;
}

export interface Analysis {
  id: string;
  query: string;
  status: AnalysisStatus;
  result: ReportResult | null;
  error: string | null;
  execution_time_ms: number | null;
  created_at: string;
  agent_runs: AgentRun[];
}

export interface AnalysisListResponse {
  items: Analysis[];
  total: number;
  limit: number;
  offset: number;
}

export interface FinancialMetric {
  id: string;
  company_id: string;
  document_id: string;
  metric_name: string;
  value: number;
  unit: string;
  period: string;
  year: number | null;
  source_page: number | null;
  confidence: number;
  created_at: string;
}

export interface MetricSeries {
  metric_name: string;
  unit: string;
  points: { year: number; value: number }[];
}

export interface DashboardStats {
  documents_total: number;
  companies_total: number;
  indexed_pages_total: number;
  embeddings_total: number;
  analyses_total: number;
  documents_by_status: Record<string, number>;
  avg_query_latency_ms: number | null;
  cache_hit_rate: number;
  cache_hits: number;
  cache_misses: number;
  recent_documents: Document[];
  recent_analysis_queries: string[];
}

export interface ApiErrorBody {
  error: { code: string; message: string };
}

// SSE event shapes from POST /api/query
export interface AgentStatusEvent {
  event: "agent_status";
  agent: string;
  status: AgentRunStatus;
  execution_time_ms: number | null;
  error: string | null;
}

export interface FinalEvent {
  event: "final";
  analysis_id: string;
  report: ReportResult;
}

export type QueryStreamEvent = AgentStatusEvent | FinalEvent;
