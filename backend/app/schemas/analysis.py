import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.analysis import AgentRunStatus, AnalysisStatus

if TYPE_CHECKING:
    from app.models.analysis import Analysis


class AnalyzeRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)


class AgentRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_name: str
    status: AgentRunStatus
    step_order: int
    input: dict[str, Any] | None
    output: dict[str, Any] | None
    error: str | None
    cache_hit: bool
    execution_time_ms: int | None
    created_at: datetime


class AnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    query: str
    title: str
    status: AnalysisStatus
    result: dict[str, Any] | None
    error: str | None
    execution_time_ms: int | None
    created_at: datetime
    agent_runs: list[AgentRunRead] = []


class AnalysisSummary(BaseModel):
    """Lightweight shape for the Recent Research list — omits the
    (potentially large) `result`/`agent_runs` payload that
    `GET /api/analyses/{id}` returns, since the list view only needs
    enough to render a row and decide what to open."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    query: str
    title: str
    status: AnalysisStatus
    created_at: datetime
    execution_time_ms: int | None
    confidence: float | None = None
    insufficient_evidence: bool | None = None

    @classmethod
    def from_analysis(cls, analysis: "Analysis") -> "AnalysisSummary":
        result = analysis.result or {}
        return cls(
            id=analysis.id,
            query=analysis.query,
            title=analysis.title,
            status=analysis.status,
            created_at=analysis.created_at,
            execution_time_ms=analysis.execution_time_ms,
            confidence=result.get("confidence"),
            insufficient_evidence=result.get("insufficient_evidence"),
        )


class AnalysisListResponse(BaseModel):
    items: list[AnalysisSummary]
    total: int
    limit: int
    offset: int
