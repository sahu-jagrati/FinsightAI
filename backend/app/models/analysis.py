"""analyses + agent_runs tables (Section 20) — a persisted record of every
research query and the multi-agent trace that produced its answer
(Section 25: Agent Observability).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.types import GUID

# Real JSONB on Postgres (efficient, queryable); portable JSON (TEXT-backed)
# everywhere else so these tables can join the SQLite test schema instead
# of needing their own Postgres-only fixture like `document_chunks` does.
_JSONType = JSON().with_variant(JSONB(), "postgresql")


class AnalysisStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentRunStatus(str, enum.Enum):
    WAITING = "waiting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Analysis(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "analyses"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    query: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(200))
    """Short label for the Recent Research list — derived from `query` at
    persist time (Section: Research History), never re-derived at read
    time so it stays stable even if the title-generation heuristic later
    changes."""
    # values_callable: bind/read the member *value* ("pending"), matching
    # what the Alembic migration actually put in the Postgres enum type —
    # see the identical comment on Document.document_type.
    status: Mapped[AnalysisStatus] = mapped_column(
        SAEnum(
            AnalysisStatus, name="analysis_status", values_callable=lambda e: [m.value for m in e]
        ),
        default=AnalysisStatus.PENDING,
        index=True,
    )
    result: Mapped[dict | None] = mapped_column(_JSONType)
    """The final ReportResult, serialized (executive summary, findings,
    comparison table, calculations, sources)."""
    error: Mapped[str | None] = mapped_column(Text)
    execution_time_ms: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    agent_runs: Mapped[list["AgentRun"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", passive_deletes=True
    )


class AgentRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "agent_runs"

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("analyses.id", ondelete="CASCADE"), index=True
    )
    agent_name: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[AgentRunStatus] = mapped_column(
        SAEnum(
            AgentRunStatus,
            name="agent_run_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=AgentRunStatus.WAITING,
    )
    step_order: Mapped[int] = mapped_column(Integer, default=0)
    input: Mapped[dict | None] = mapped_column(_JSONType)
    output: Mapped[dict | None] = mapped_column(_JSONType)
    error: Mapped[str | None] = mapped_column(Text)
    cache_hit: Mapped[bool] = mapped_column(default=False)
    execution_time_ms: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    analysis: Mapped["Analysis"] = relationship(back_populates="agent_runs")
