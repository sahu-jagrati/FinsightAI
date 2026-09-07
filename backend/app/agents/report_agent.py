"""Report Generation Agent (Section 15) + hallucination prevention
(Section 16).

Combines evidence, extracted metrics, calculations, and comparison
insights into the final answer. Two things make this "source-grounded"
rather than a bare LLM call:

1.  If retrieval found nothing, the LLM is never even asked — the report
    is the fixed "insufficient evidence" response, verbatim per Section 16.
2.  The prompt hands the LLM ONLY the retrieved evidence text (never
    "answer from general knowledge"), and if the configured provider can't
    produce real content (the mock provider, or any provider returning
    empty content), the executive summary falls back to a template built
    deterministically from the comparison insights / calculations /
    evidence already computed — still fully grounded, just not
    LLM-phrased. The app never fabricates a number either way.
"""

from app.agents.state import Citation, ReportResult, ResearchState
from app.rag.llm.base import LLMMessage

INSUFFICIENT_EVIDENCE_MESSAGE = (
    "I couldn't find sufficient evidence in the indexed documents to answer this reliably."
)
_MAX_CONTEXT_ITEMS = 6
_MAX_SNIPPET_CHARS = 500

_SYSTEM_PROMPT = (
    "You are FinSight AI, a financial research analyst. Answer the user's question using "
    "ONLY the evidence provided below — never use outside knowledge and never invent a "
    "number that isn't in the evidence. Be concise (2-4 sentences). If the evidence doesn't "
    "actually answer the question, say so explicitly instead of guessing."
)


def _format_source(item) -> str:
    label = f"{item.document_filename or 'source'}"
    if item.page_number:
        label += f", p. {item.page_number}"
    if item.company:
        label = f"{item.company} — {label}"
    return label


def _build_context(state: ResearchState) -> str:
    lines = []
    for i, item in enumerate(state.evidence[:_MAX_CONTEXT_ITEMS], start=1):
        snippet = item.content[:_MAX_SNIPPET_CHARS]
        lines.append(f"[{i}] ({_format_source(item)}): {snippet}")
    return "\n\n".join(lines)


def _template_summary(state: ResearchState) -> str:
    """Deterministic, fully-grounded fallback used when the LLM has
    nothing real to say (e.g. the mock provider) — never fabricates."""
    if state.comparison_insights:
        return " ".join(state.comparison_insights)

    if state.calculations:
        c = state.calculations[0]
        return f"{c.operation.value.replace('_', ' ').upper()}: {c.result:.2%} ({c.formula})."

    top = state.evidence[0]
    return f"Based on {_format_source(top)}: {top.content[:280].strip()}"


def _compute_confidence(state: ResearchState) -> float:
    if not state.evidence:
        return 0.0
    avg_evidence_score = sum(e.score for e in state.evidence) / len(state.evidence)
    confidence = max(0.0, min(1.0, avg_evidence_score))

    wanted_calculation = bool(
        set(state.understanding.operations) & {"cagr", "growth", "margin", "ratio"}
    )
    if wanted_calculation and not state.calculations:
        confidence *= 0.5  # asked for a number we couldn't actually compute

    return round(confidence, 3)


async def run_report_agent(state: ResearchState) -> None:
    trace = state.new_trace("report_agent")
    trace.start(evidence_count=len(state.evidence))

    try:
        if not state.evidence:
            state.report = ReportResult(
                executive_summary=INSUFFICIENT_EVIDENCE_MESSAGE,
                key_findings=[],
                comparison_table=[],
                calculations=[],
                sources=[],
                citations=[],
                confidence=0.0,
                insufficient_evidence=True,
            )
            trace.complete(insufficient_evidence=True)
            return

        context = _build_context(state)
        response = await state.llm.chat(
            [
                LLMMessage("system", _SYSTEM_PROMPT),
                LLMMessage(
                    "user", f"Question: {state.query}\n\nEvidence:\n{context}"
                ),
            ]
        )

        executive_summary = response.content.strip()
        used_fallback = not executive_summary or executive_summary.startswith("[mock LLM")
        if used_fallback:
            executive_summary = _template_summary(state)

        key_findings = list(state.comparison_insights)
        if not key_findings:
            for c in state.calculations[:5]:
                key_findings.append(
                    f"{c.operation.value.replace('_', ' ').title()}: {c.result:.2%}"
                )

        sources = []
        citations = []
        seen = set()
        for item in state.evidence:
            label = _format_source(item)
            if label not in seen:
                seen.add(label)
                sources.append(label)
                citations.append(
                    Citation(
                        label=label,
                        company=item.company,
                        document_id=item.document_id,
                        document_filename=item.document_filename,
                        page_number=item.page_number,
                    )
                )

        state.report = ReportResult(
            executive_summary=executive_summary,
            key_findings=key_findings,
            comparison_table=state.comparison_rows,
            calculations=state.calculations,
            sources=sources,
            citations=citations,
            confidence=_compute_confidence(state),
            insufficient_evidence=False,
        )
        trace.complete(
            used_llm_fallback=used_fallback,
            confidence=state.report.confidence,
            source_count=len(sources),
        )
    except Exception as exc:  # noqa: BLE001
        trace.fail(str(exc))
        raise
