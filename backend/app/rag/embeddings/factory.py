"""Process-wide default `EmbeddingService`. Call sites that want the real
model use `get_embedding_service()`; tests construct
`tests.fakes.FakeEmbeddingService` directly and pass it in instead of
touching this module.
"""

from functools import lru_cache

from app.rag.embeddings.base import EmbeddingService
from app.rag.embeddings.huggingface import HuggingFaceEmbeddingService


@lru_cache
def get_embedding_service() -> EmbeddingService:
    return HuggingFaceEmbeddingService()
