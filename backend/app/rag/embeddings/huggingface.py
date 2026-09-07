"""Real embedding backend: `sentence-transformers` running a Hugging Face
model locally (CPU) — no external API key required (Section 7/17 of the
brief: "Use a configurable Hugging Face embedding model").

The model is loaded lazily (first call, not import time) and cached as a
process-wide singleton, since loading it is a multi-hundred-millisecond-to-
several-second operation that should happen once per worker process, not
per request. Encoding runs in a thread via `asyncio.to_thread` because
`sentence-transformers` is synchronous/CPU-bound and would otherwise block
the event loop.
"""

import asyncio
import threading

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("embeddings")

# BGE models are trained with an instruction prefix on the QUERY side only
# for retrieval tasks — passages are embedded as-is. Harmless no-op for
# models that don't expect it.
_BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


class HuggingFaceEmbeddingService:
    """Lazily loads `settings.EMBEDDING_MODEL_NAME` via sentence-transformers."""

    def __init__(self, model_name: str | None = None, dimensions: int | None = None):
        self.model_name = model_name or settings.EMBEDDING_MODEL_NAME
        self.dimensions = dimensions or settings.EMBEDDING_DIMENSIONS
        self._model = None
        self._lock = threading.Lock()

    def _load_model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:  # re-check inside the lock
                    from sentence_transformers import SentenceTransformer

                    logger.info("embeddings.loading_model", model=self.model_name)
                    self._model = SentenceTransformer(
                        self.model_name, device=settings.EMBEDDING_DEVICE
                    )
                    logger.info("embeddings.model_ready", model=self.model_name)
        return self._model

    def _encode(self, texts: list[str]) -> list[list[float]]:
        model = self._load_model()
        vectors = model.encode(
            texts,
            batch_size=settings.EMBEDDING_BATCH_SIZE,
            normalize_embeddings=True,  # so cosine similarity == dot product
            show_progress_bar=False,
        )
        return vectors.tolist()

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await asyncio.to_thread(self._encode, texts)

    async def embed_query(self, text: str) -> list[float]:
        vectors = await asyncio.to_thread(self._encode, [_BGE_QUERY_INSTRUCTION + text])
        return vectors[0]
