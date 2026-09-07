from pydantic import BaseModel

from app.schemas.document import DocumentRead


class SystemComponentStatus(BaseModel):
    documents_total: int
    companies_total: int
    indexed_pages_total: int
    embeddings_total: int
    analyses_total: int
    documents_by_status: dict[str, int]
    avg_query_latency_ms: float | None
    cache_hit_rate: float
    cache_hits: int
    cache_misses: int


class DashboardStats(SystemComponentStatus):
    recent_documents: list[DocumentRead]
    recent_analysis_queries: list[str]
