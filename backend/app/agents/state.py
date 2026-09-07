"""Shared data shapes passed between agents.

Deliberately plain dataclasses, not a framework's graph/node state object —
Section 36 asks to avoid unnecessary complexity, and a hand-rolled
supervisor over asyncio is easier to reason about and observe (Section 25)
than a black-box graph runtime for a pipeline this size.
"""

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.embeddings.base import EmbeddingService
from app.rag.llm.base import LLMProvider
from app.rag.retrieval.reranker import Reranker
from app.services.calculations import CalculationResult


@dataclass
class QueryUnderstanding:
    companies: list[str] = field(default_factory=list)
    """Company names as matched against the `companies` table."""
    metrics: list[str] = field(default_factory=list)
    years: list[int] = field(default_factory=list)
    document_types: list[str] = field(default_factory=list)
    operations: list[str] = field(default_factory=list)
    """e.g. "cagr", "growth", "margin", "comparison", "summary"."""
    is_comparison: bool = False


@dataclass
class EvidenceItem:
    chunk_id: uuid.UUID
    content: str
    company: str | None
    document_filename: str | None
    page_number: int | None
    section: str | None
    score: float
    document_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None


@dataclass
class ExtractedMetric:
    company: str
    metric_name: str
    value: float
    unit: str
    period: str
    year: int | None
    source_page: int | None
    source_document: str | None
    confidence: float
    document_id: uuid.UUID | None = None
    chunk_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None


@dataclass
class ComparisonRow:
    company: str
    metric: str
    values_by_year: dict[int, float]
    calculation: CalculationResult | None = None


@dataclass
class AgentTrace:
    agent_name: str
    status: str = "waiting"  # waiting | running | completed | failed
    started_at: float | None = None
    execution_time_ms: int | None = None
    input: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    cache_hit: bool = False

    def start(self, **input_kwargs: Any) -> None:
        self.status = "running"
        self.started_at = time.monotonic()
        self.input = input_kwargs

    def complete(self, **output_kwargs: Any) -> None:
        self.status = "completed"
        if self.started_at is not None:
            self.execution_time_ms = int((time.monotonic() - self.started_at) * 1000)
        self.output = output_kwargs

    def fail(self, error: str) -> None:
        self.status = "failed"
        if self.started_at is not None:
            self.execution_time_ms = int((time.monotonic() - self.started_at) * 1000)
        self.error = error


@dataclass
class Citation:
    """A structured, clickable version of a source string (Section 24) —
    enough to open the exact document/page in the frontend's document
    viewer, not just display text."""

    label: str
    company: str | None
    document_id: uuid.UUID | None
    document_filename: str | None
    page_number: int | None


@dataclass
class ReportResult:
    executive_summary: str
    key_findings: list[str]
    comparison_table: list[ComparisonRow]
    calculations: list[CalculationResult]
    sources: list[str]
    citations: list[Citation]
    confidence: float
    insufficient_evidence: bool = False


@dataclass
class ResearchState:
    query: str
    db: AsyncSession
    llm: LLMProvider
    embedding_service: EmbeddingService
    reranker: Reranker
    session_factory: Callable[[], AsyncSession]
    """Opens a fresh session bound to the same database as `db`. Used for
    genuine concurrent DB reads (Section 31) — see the Retrieval Agent —
    since `db` itself, a single `AsyncSession`, cannot safely be used from
    more than one coroutine at a time."""

    understanding: QueryUnderstanding = field(default_factory=QueryUnderstanding)
    evidence: list[EvidenceItem] = field(default_factory=list)
    extracted_metrics: list[ExtractedMetric] = field(default_factory=list)
    calculations: list[CalculationResult] = field(default_factory=list)
    comparison_rows: list[ComparisonRow] = field(default_factory=list)
    comparison_insights: list[str] = field(default_factory=list)
    report: ReportResult | None = None

    trace: list[AgentTrace] = field(default_factory=list)

    def new_trace(self, agent_name: str) -> AgentTrace:
        t = AgentTrace(agent_name=agent_name)
        self.trace.append(t)
        return t
