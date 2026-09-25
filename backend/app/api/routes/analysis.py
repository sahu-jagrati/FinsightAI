"""Research/analysis endpoints (Section 19/21).

`POST /api/analyze` runs the full supervisor pipeline synchronously and
persists the result + agent trace — the "review previous analyses" flow.
`POST /api/query` streams the same pipeline's progress via Server-Sent
Events, for the live agent execution panel (Section 21/25).
"""

import json
import uuid

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.supervisor import run_research, stream_research
from app.db.session import get_db, get_session_factory
from app.schemas.analysis import AnalysisListResponse, AnalysisRead, AnalysisSummary, AnalyzeRequest
from app.services.analysis_service import (
    delete_analysis,
    get_analysis,
    list_analyses,
    persist_analysis,
    serialize_report,
)

router = APIRouter(tags=["research"])


@router.post("/analyze", response_model=AnalysisRead)
async def analyze(
    payload: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> AnalysisRead:
    state = await run_research(payload.query, db, session_factory=session_factory)
    analysis = await persist_analysis(db, state)
    await db.commit()
    return AnalysisRead.model_validate(analysis)


@router.post("/query")
async def query(
    payload: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> StreamingResponse:
    """SSE stream of `{"event": "agent_status", ...}` frames as each agent
    finishes, followed by one `{"event": "final", "report": {...}}` frame.
    The pipeline result is persisted the same as `/analyze` once complete.
    """

    async def event_stream():
        final_state = None
        async for event in stream_research(payload.query, db, session_factory=session_factory):
            if event.get("event") == "final":
                final_state = event["state"]
                analysis = await persist_analysis(db, final_state)
                await db.commit()
                payload_out = {
                    "event": "final",
                    "analysis_id": str(analysis.id),
                    "report": serialize_report(final_state.report),
                }
                yield f"data: {json.dumps(payload_out)}\n\n"
            else:
                yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/analyses", response_model=AnalysisListResponse)
async def get_analyses(
    limit: int = 20, offset: int = 0, search: str | None = None, db: AsyncSession = Depends(get_db)
) -> AnalysisListResponse:
    """Recent Research list (Section: Research History). Returns the
    lightweight `AnalysisSummary` shape — open `GET /analyses/{id}` for
    the full persisted report, which never re-runs the agent pipeline."""
    limit = max(1, min(limit, 100))
    items, total = await list_analyses(db, limit=limit, offset=offset, search=search)
    return AnalysisListResponse(
        items=[AnalysisSummary.from_analysis(a) for a in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/analyses/{analysis_id}", response_model=AnalysisRead)
async def get_analysis_by_id(
    analysis_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> AnalysisRead:
    """Loads a previously persisted analysis verbatim — no LLM/agent call,
    just a read of `result` as it was saved when the query first ran."""
    analysis = await get_analysis(db, analysis_id)
    return AnalysisRead.model_validate(analysis)


@router.delete("/analyses/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_analysis_by_id(
    analysis_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> None:
    await delete_analysis(db, analysis_id)
    await db.commit()
