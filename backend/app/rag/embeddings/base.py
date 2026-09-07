"""Embedding service interface.

Every caller (chunker/indexing pipeline, retrieval agent) depends on this
`Protocol`, never on `sentence_transformers` directly — that's what lets
tests substitute a fast deterministic fake and lets the embedding model be
swapped via `EMBEDDING_MODEL_NAME` without touching call sites.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingService(Protocol):
    dimensions: int

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed chunk/passage text for storage."""
        ...

    async def embed_query(self, text: str) -> list[float]:
        """Embed a user query. Some models (e.g. BGE) recommend a different
        instruction prefix for queries vs. documents — implementations
        handle that internally."""
        ...
