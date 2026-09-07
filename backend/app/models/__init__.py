"""SQLAlchemy ORM models.

Every model module must be imported here so Alembic autogenerate (and
`Base.metadata.create_all` in tests) can see it — see `alembic/env.py`.

`users`, `companies`, `documents` (Phase 2), `document_chunks` (Phase 3),
`analyses` / `agent_runs` / `financial_metrics` (Phase 7/8).
"""

from app.models.analysis import AgentRun, AgentRunStatus, Analysis, AnalysisStatus
from app.models.company import Company
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import DocumentStatus, DocumentType
from app.models.financial_metric import FinancialMetric
from app.models.user import User

__all__ = [
    "AgentRun",
    "AgentRunStatus",
    "Analysis",
    "AnalysisStatus",
    "Company",
    "Document",
    "DocumentChunk",
    "DocumentStatus",
    "DocumentType",
    "FinancialMetric",
    "User",
]
