"""Supervisor / Router Agent (Section 10/35).

    User -> Supervisor -> [Retrieval, Extraction, Calculation, Comparison]* -> Report -> Supervisor -> Answer

The supervisor decides which agents a given question actually needs
instead of always running the full set: extraction only runs if retrieval
found anything, calculation only runs if the query asked for one AND
extraction found dated numbers to compute over, comparison only runs for
multi-company questions. A single agent failing doesn't take down the
whole request — its trace records the failure (Section 25) and the
supervisor moves on with whatever it has, since a partial grounded answer
beats a hard 500.

`stream_research` is the single implementation — it's an async generator
that yields an event after every agent finishes, which is what
`POST /api/query`'s SSE endpoint streams to the frontend's agent execution
panel (Section 21/25) in real time. `run_research` (used by the
non-streaming `POST /api/analyze`) just drains it and returns the final
state, so there's exactly one orchestration path, not two that could drift.
"""

from collections.abc import AsyncGenerator, Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.calculation_agent import run_calculation_agent
from app.agents.comparison_agent import run_comparison_agent
from app.agents.extraction_agent import run_extraction_agent
from app.agents.query_understanding import understand_query
from app.agents.report_agent import INSUFFICIENT_EVIDENCE_MESSAGE, run_report_agent
from app.agents.retrieval_agent import run_retrieval_agent
from app.agents.state import AgentTrace, ReportResult, ResearchState
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.company import Company
from app.rag.embeddings.base import EmbeddingService
from app.rag.embeddings.factory import get_embedding_service
from app.rag.llm.base import LLMProvider
from app.rag.llm.factory import get_llm_provider
from app.rag.retrieval.factory import get_reranker
from app.rag.retrieval.reranker import Reranker

logger = get_logger("supervisor")

_CALCULATION_OPERATIONS = {"cagr", "growth", "margin", "ratio"}


async def _list_company_names(db: AsyncSession) -> list[str]:
    result = await db.execute(select(Company.name))
    return list(result.scalars().all())


async def _try_run(agent_fn, state: ResearchState) -> None:
    try:
        await agent_fn(state)
    except Exception:  # noqa: BLE001 - already logged/traced inside the agent
        logger.warning("supervisor.agent_failed", agent=agent_fn.__name__)


def _trace_event(trace: AgentTrace) -> dict[str, Any]:
    return {
        "event": "agent_status",
        "agent": trace.agent_name,
        "status": trace.status,
        "execution_time_ms": trace.execution_time_ms,
        "error": trace.error,
    }


def _fallback_report() -> ReportResult:
    return ReportResult(
        executive_summary=INSUFFICIENT_EVIDENCE_MESSAGE,
        key_findings=[],
        comparison_table=[],
        calculations=[],
        sources=[],
        citations=[],
        confidence=0.0,
        insufficient_evidence=True,
    )


async def stream_research(
    query: str,
    db: AsyncSession,
    *,
    llm: LLMProvider | None = None,
    embedding_service: EmbeddingService | None = None,
    reranker: Reranker | None = None,
    session_factory: Callable[[], AsyncSession] | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    state = ResearchState(
        query=query,
        db=db,
        llm=llm or get_llm_provider(),
        embedding_service=embedding_service or get_embedding_service(),
        reranker=reranker or get_reranker(),
        session_factory=session_factory or AsyncSessionLocal,
    )

    supervisor_trace = state.new_trace("supervisor")
    supervisor_trace.start(query=query)
    yield _trace_event(supervisor_trace)

    try:
        known_companies = await _list_company_names(db)
        state.understanding = await understand_query(query, known_companies)

        await _try_run(run_retrieval_agent, state)
        yield _trace_event(state.trace[-1])

        if state.evidence:
            await _try_run(run_extraction_agent, state)
            yield _trace_event(state.trace[-1])

            wants_calculation = bool(
                set(state.understanding.operations) & _CALCULATION_OPERATIONS
            )
            if wants_calculation and state.extracted_metrics:
                await _try_run(run_calculation_agent, state)
                yield _trace_event(state.trace[-1])

            is_multi_company_comparison = (
                state.understanding.is_comparison and len(state.understanding.companies) >= 2
            )
            if is_multi_company_comparison and state.comparison_rows:
                await _try_run(run_comparison_agent, state)
                yield _trace_event(state.trace[-1])

        await _try_run(run_report_agent, state)
        yield _trace_event(state.trace[-1])

        if state.report is None:
            # report_agent itself failed unexpectedly (not just "no
            # evidence" — that path always sets a report). Never surface a
            # bare 500 for a research query; degrade to the same
            # insufficient-evidence contract instead.
            state.report = _fallback_report()

        supervisor_trace.complete(
            agents_run=[t.agent_name for t in state.trace if t.agent_name != "supervisor"],
            evidence_count=len(state.evidence),
        )
    except Exception as exc:  # noqa: BLE001 - the caller must always get a final state
        logger.exception("supervisor.unexpected_error", query=query)
        supervisor_trace.fail(str(exc))
        if state.report is None:
            state.report = _fallback_report()

    yield _trace_event(supervisor_trace)
    yield {"event": "final", "state": state}


async def run_research(
    query: str,
    db: AsyncSession,
    *,
    llm: LLMProvider | None = None,
    embedding_service: EmbeddingService | None = None,
    reranker: Reranker | None = None,
    session_factory: Callable[[], AsyncSession] | None = None,
) -> ResearchState:
    final_state: ResearchState | None = None
    async for event in stream_research(
        query,
        db,
        llm=llm,
        embedding_service=embedding_service,
        reranker=reranker,
        session_factory=session_factory,
    ):
        if event.get("event") == "final":
            final_state = event["state"]
    assert final_state is not None  # stream_research always yields a "final" event
    return final_state
