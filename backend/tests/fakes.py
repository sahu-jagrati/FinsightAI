"""Test doubles shared across the suite."""

import hashlib
import math
import re

_WORD_RE = re.compile(r"[a-z0-9]+")


class FakeEmbeddingService:
    """Deterministic, dependency-free stand-in for
    `HuggingFaceEmbeddingService` (Section 30 — tests shouldn't need to
    download a model). Implements a hashed bag-of-words embedding: each
    word hashes into one of `dimensions` buckets, so texts sharing
    vocabulary land closer together in cosine similarity — enough to test
    retrieval ranking logic meaningfully, unlike a purely random vector.
    """

    def __init__(self, dimensions: int = 384):
        self.dimensions = dimensions

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dimensions
        for word in _WORD_RE.findall(text.lower()):
            bucket = int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dimensions
            vec[bucket] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class FakeReranker:
    """Deterministic stand-in for `CrossEncoderReranker`: scores by word
    overlap between the query and each candidate's content, instead of
    downloading a cross-encoder model."""

    async def rerank(self, query, candidates, top_n):
        query_words = set(_WORD_RE.findall(query.lower()))
        for candidate in candidates:
            chunk_words = set(_WORD_RE.findall(candidate.chunk.content.lower()))
            candidate.rerank_score = float(len(query_words & chunk_words))
        ranked = sorted(candidates, key=lambda c: c.rerank_score, reverse=True)
        return ranked[:top_n]
