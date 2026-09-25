import { API_BASE_URL } from "@/lib/config";
import type {
  Analysis,
  AnalysisListResponse,
  ApiErrorBody,
  Company,
  DashboardStats,
  Document,
  DocumentListResponse,
  DocumentType,
  FinancialMetric,
  MetricSeries,
  QueryStreamEvent,
} from "@/types/api";

export class ApiError extends Error {
  code: string;
  status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
    cache: "no-store",
  });

  if (!res.ok) {
    let body: ApiErrorBody | null = null;
    try {
      body = await res.json();
    } catch {
      // non-JSON error body (e.g. a 5xx from an upstream proxy)
    }
    throw new ApiError(
      res.status,
      body?.error?.code ?? "unknown_error",
      body?.error?.message ?? res.statusText ?? "Something went wrong.",
    );
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// --- Documents -------------------------------------------------------------

export function listDocuments(params?: {
  search?: string;
  document_type?: DocumentType;
  company_id?: string;
  limit?: number;
  offset?: number;
}): Promise<DocumentListResponse> {
  const qs = new URLSearchParams();
  if (params?.search) qs.set("search", params.search);
  if (params?.document_type) qs.set("document_type", params.document_type);
  if (params?.company_id) qs.set("company_id", params.company_id);
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.offset) qs.set("offset", String(params.offset));
  const suffix = qs.toString() ? `?${qs}` : "";
  return request(`/api/documents${suffix}`);
}

export function getDocument(id: string): Promise<Document> {
  return request(`/api/documents/${id}`);
}

export function deleteDocument(id: string): Promise<void> {
  return request(`/api/documents/${id}`, { method: "DELETE" });
}

export async function uploadDocument(input: {
  file: File;
  companyName?: string;
  documentType: DocumentType;
  reportingPeriod?: string;
  source?: string;
}): Promise<Document> {
  const form = new FormData();
  form.append("file", input.file);
  if (input.companyName) form.append("company_name", input.companyName);
  form.append("document_type", input.documentType);
  if (input.reportingPeriod) form.append("reporting_period", input.reportingPeriod);
  if (input.source) form.append("source", input.source);

  const res = await fetch(`${API_BASE_URL}/api/documents/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const body: ApiErrorBody = await res.json().catch(() => ({
      error: { code: "unknown_error", message: res.statusText },
    }));
    throw new ApiError(res.status, body.error.code, body.error.message);
  }
  return res.json();
}

// --- Companies ---------------------------------------------------------

export function listCompanies(): Promise<Company[]> {
  return request(`/api/companies`);
}

export function getCompany(id: string): Promise<Company> {
  return request(`/api/companies/${id}`);
}

export function getCompanyMetrics(id: string): Promise<MetricSeries[]> {
  return request(`/api/companies/${id}/metrics`);
}

// --- Metrics -------------------------------------------------------------

export function listMetrics(params?: {
  company_id?: string;
  metric_name?: string;
}): Promise<FinancialMetric[]> {
  const qs = new URLSearchParams();
  if (params?.company_id) qs.set("company_id", params.company_id);
  if (params?.metric_name) qs.set("metric_name", params.metric_name);
  const suffix = qs.toString() ? `?${qs}` : "";
  return request(`/api/metrics${suffix}`);
}

// --- Dashboard -----------------------------------------------------------

export function getDashboardStats(): Promise<DashboardStats> {
  return request(`/api/dashboard/stats`);
}

// --- Research / analyses -------------------------------------------------

export function analyze(query: string): Promise<Analysis> {
  return request(`/api/analyze`, { method: "POST", body: JSON.stringify({ query }) });
}

export function listAnalyses(params?: {
  limit?: number;
  offset?: number;
  search?: string;
}): Promise<AnalysisListResponse> {
  const qs = new URLSearchParams();
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.offset) qs.set("offset", String(params.offset));
  if (params?.search) qs.set("search", params.search);
  const suffix = qs.toString() ? `?${qs}` : "";
  return request(`/api/analyses${suffix}`);
}

export function getAnalysis(id: string): Promise<Analysis> {
  return request(`/api/analyses/${id}`);
}

export function deleteAnalysis(id: string): Promise<void> {
  return request(`/api/analyses/${id}`, { method: "DELETE" });
}

/**
 * Streams `POST /api/query`'s Server-Sent Events. Parses the
 * `data: {...}\n\n` framing by hand via the fetch body reader rather than
 * `EventSource` — EventSource can't send a JSON POST body, and this only
 * ever needs one stream per call, not automatic reconnection.
 */
export async function* streamQuery(
  query: string,
  signal?: AbortSignal,
): AsyncGenerator<QueryStreamEvent> {
  const res = await fetch(`${API_BASE_URL}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
    signal,
  });

  if (!res.ok || !res.body) {
    const body: ApiErrorBody = await res.json().catch(() => ({
      error: { code: "unknown_error", message: res.statusText },
    }));
    throw new ApiError(res.status, body.error.code, body.error.message);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sepIndex: number;
    while ((sepIndex = buffer.indexOf("\n\n")) !== -1) {
      const rawEvent = buffer.slice(0, sepIndex);
      buffer = buffer.slice(sepIndex + 2);
      const line = rawEvent.split("\n").find((l) => l.startsWith("data: "));
      if (line) {
        yield JSON.parse(line.slice("data: ".length)) as QueryStreamEvent;
      }
    }
  }
}
