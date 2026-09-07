import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.analysis import AgentRunStatus, AnalysisStatus


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
    status: AnalysisStatus
    result: dict[str, Any] | None
    error: str | None
    execution_time_ms: int | None
    created_at: datetime
    agent_runs: list[AgentRunRead] = []


class AnalysisListResponse(BaseModel):
    items: list[AnalysisRead]
    total: int
    limit: int
    offset: int
