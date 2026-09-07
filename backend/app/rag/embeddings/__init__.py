"""Embedding generation. `base.EmbeddingService` is the interface every
retrieval/ingestion function depends on; `huggingface.py` is the real
(sentence-transformers, CPU) implementation used in production. Tests
inject a deterministic fake instead of downloading a model — see
`tests/fakes.py`.
"""

from app.rag.embeddings.base import EmbeddingService
from app.rag.embeddings.factory import get_embedding_service

__all__ = ["EmbeddingService", "get_embedding_service"]
