"""Reranking (Section 7/11) — a second, more expensive relevance pass over
the hybrid search candidate pool.

Hybrid search's dense+sparse fusion is a good *recall* mechanism (cheap,
scales to millions of chunks) but a mediocre *precision* mechanism — bag-of-
embeddings/keyword scores don't actually read the query against each
candidate. A cross-encoder does: it scores each (query, chunk) pair
jointly, which is far more accurate but too slow to run over the whole
corpus — hence running it only over hybrid search's already-narrowed
top-N pool.
"""

import asyncio
import threading
from typing import Protocol

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.retrieval.vector_store import ScoredChunk

logger = get_logger("reranker")


class Reranker(Protocol):
    async def rerank(
        self, query: str, candidates: list[ScoredChunk], top_n: int
    ) -> list[ScoredChunk]: ...


class CrossEncoderReranker:
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.RERANKER_MODEL_NAME
        self._model = None
        self._lock = threading.Lock()

    def _load_model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import CrossEncoder

                    logger.info("reranker.loading_model", model=self.model_name)
                    self._model = CrossEncoder(self.model_name)
                    logger.info("reranker.model_ready", model=self.model_name)
        return self._model

    def _score(self, query: str, candidates: list[ScoredChunk]) -> list[float]:
        model = self._load_model()
        pairs = [(query, c.chunk.content) for c in candidates]
        return [float(s) for s in model.predict(pairs)]

    async def rerank(
        self, query: str, candidates: list[ScoredChunk], top_n: int
    ) -> list[ScoredChunk]:
        if not candidates:
            return []

        scores = await asyncio.to_thread(self._score, query, candidates)
        for candidate, score in zip(candidates, scores, strict=True):
            candidate.rerank_score = score

        ranked = sorted(candidates, key=lambda c: c.rerank_score, reverse=True)
        return ranked[:top_n]


class IdentityReranker:
    """No-op reranker — keeps hybrid search's fused ordering. Used when
    `RERANKER_ENABLED=false`, e.g. to save CPU/latency in a demo run."""

    async def rerank(
        self, query: str, candidates: list[ScoredChunk], top_n: int
    ) -> list[ScoredChunk]:
        return candidates[:top_n]
