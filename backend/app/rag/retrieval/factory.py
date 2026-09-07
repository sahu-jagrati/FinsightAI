from functools import lru_cache

from app.core.config import settings
from app.rag.retrieval.reranker import CrossEncoderReranker, IdentityReranker, Reranker


@lru_cache
def get_reranker() -> Reranker:
    if not settings.RERANKER_ENABLED:
        return IdentityReranker()
    return CrossEncoderReranker()
