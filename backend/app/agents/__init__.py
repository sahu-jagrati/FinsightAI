"""Supervisor + specialized agents (Sections 10-16, 35).

    User -> Supervisor -> Retrieval -> Extraction -> Calculation -> Comparison -> Report -> Supervisor -> Answer

`supervisor.run_research()` is the entrypoint every API route calls — it
decides which of the specialized agents below a given question actually
needs rather than always running the full chain.
"""

from app.agents.supervisor import run_research

__all__ = ["run_research"]
