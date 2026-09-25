"""Persists a completed `ResearchState` as an `Analysis` + its `AgentRun`
trace (Section 20/25), and reads them back for `GET /api/analyses*`
(Research History / "Recent Research" — loading a past analysis never
re-runs the agent pipeline, it just deserializes the already-persisted
`result`).
"""

import re
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.state import Citation, ComparisonRow, ReportResult, ResearchState
from app.core.exceptions import NotFoundError
from app.models.analysis import AgentRun, AgentRunStatus, Analysis, AnalysisStatus
from app.services.calculations import CalculationResult

_TITLE_MAX_LEN = 200
_TITLE_TRUNCATE_AT = 80


def generate_title(query: str) -> str:
    """Derives a short, human-scannable title from the raw query — no LLM
    call, so this never adds latency or cost to persisting an analysis.
    Collapses whitespace and truncates on a word boundary."""
    collapsed = re.sub(r"\s+", " ", query).strip()
    if len(collapsed) <= _TITLE_TRUNCATE_AT:
        return collapsed[:_TITLE_MAX_LEN] or "Untitled research"
    truncated = collapsed[:_TITLE_TRUNCATE_AT]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated.rstrip(",.;:") + "…"


def _serialize_calculation(c: CalculationResult) -> dict:
    return {
        "operation": c.operation.value,
        "result": c.result,
        "formula": c.formula,
        "inputs": c.inputs,
    }


def _serialize_row(row: ComparisonRow) -> dict:
    return {
        "company": row.company,
        "metric": row.metric,
        "values_by_year": {str(y): v for y, v in row.values_by_year.items()},
        "calculation": _serialize_calculation(row.calculation) if row.calculation else None,
        "unit": row.unit,
        "insufficient_reason": row.insufficient_reason,
    }


def _serialize_citation(c: Citation) -> dict:
    return {
        "label": c.label,
        "company": c.company,
        "document_id": str(c.document_id) if c.document_id else None,
        "document_filename": c.document_filename,
        "page_number": c.page_number,
    }


def serialize_report(report: ReportResult) -> dict:
    return {
        "executive_summary": report.executive_summary,
        "key_findings": report.key_findings,
        "comparison_table": [_serialize_row(r) for r in report.comparison_table],
        "calculations": [_serialize_calculation(c) for c in report.calculations],
        "sources": report.sources,
        "citations": [_serialize_citation(c) for c in report.citations],
        "confidence": report.confidence,
        "insufficient_evidence": report.insufficient_evidence,
    }


async def persist_analysis(
    db: AsyncSession, state: ResearchState, *, user_id: uuid.UUID | None = None
) -> Analysis:
    supervisor_trace = next((t for t in state.trace if t.agent_name == "supervisor"), None)
    status = AnalysisStatus.FAILED if supervisor_trace and supervisor_trace.status == "failed" else AnalysisStatus.COMPLETED

    analysis = Analysis(
        user_id=user_id,
        query=state.query,
        title=generate_title(state.query),
        status=status,
        result=serialize_report(state.report) if state.report else None,
        error=supervisor_trace.error if supervisor_trace else None,
        execution_time_ms=supervisor_trace.execution_time_ms if supervisor_trace else None,
    )
    db.add(analysis)
    await db.flush()

    for step_order, t in enumerate(state.trace):
        db.add(
            AgentRun(
                analysis_id=analysis.id,
                agent_name=t.agent_name,
                status=AgentRunStatus(t.status),
                step_order=step_order,
                input=t.input,
                output=t.output,
                error=t.error,
                cache_hit=t.cache_hit,
                execution_time_ms=t.execution_time_ms,
            )
        )
    await db.flush()
    # `analysis.agent_runs` was never populated on this Python object (the
    # AgentRun rows above were added independently, not via
    # `analysis.agent_runs.append(...)`), so serializing it (e.g.
    # `AnalysisRead.model_validate`) would trigger a lazy-load — which
    # Pydantic's synchronous attribute access can't do safely against an
    # async session ("MissingGreenlet"). Refresh it explicitly instead so
    # every caller gets an object that's safe to serialize immediately.
    await db.refresh(analysis, attribute_names=["agent_runs"])
    return analysis


async def get_analysis(db: AsyncSession, analysis_id: uuid.UUID) -> Analysis:
    result = await db.execute(
        select(Analysis)
        .options(selectinload(Analysis.agent_runs))
        .where(Analysis.id == analysis_id)
    )
    analysis = result.scalar_one_or_none()
    if analysis is None:
        raise NotFoundError(f"Analysis {analysis_id} not found.")
    return analysis


async def list_analyses(
    db: AsyncSession, *, limit: int = 20, offset: int = 0, search: str | None = None
) -> tuple[list[Analysis], int]:
    filters = []
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        filters.append(or_(Analysis.title.ilike(pattern), Analysis.query.ilike(pattern)))

    count_stmt = select(func.count()).select_from(Analysis)
    stmt = select(Analysis).options(selectinload(Analysis.agent_runs))
    for f in filters:
        count_stmt = count_stmt.where(f)
        stmt = stmt.where(f)

    total = (await db.execute(count_stmt)).scalar_one()
    result = await db.execute(stmt.order_by(Analysis.created_at.desc()).limit(limit).offset(offset))
    return list(result.scalars().all()), total


async def delete_analysis(db: AsyncSession, analysis_id: uuid.UUID) -> None:
    analysis = await get_analysis(db, analysis_id)
    await db.delete(analysis)
    await db.flush()
