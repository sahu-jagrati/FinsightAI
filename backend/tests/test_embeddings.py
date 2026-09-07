from app.rag.embeddings.huggingface import HuggingFaceEmbeddingService
from tests.fakes import FakeEmbeddingService


async def test_fake_embedding_similar_texts_score_higher_than_unrelated():
    embedder = FakeEmbeddingService(dimensions=64)
    a, b, c = await embedder.embed_documents(
        [
            "Apple reported strong iPhone revenue growth.",
            "Apple's iPhone revenue grew strongly this quarter.",
            "The cat sat on the mat in the garden.",
        ]
    )

    def cosine(x, y):
        return sum(xi * yi for xi, yi in zip(x, y, strict=True))  # unit vectors

    assert cosine(a, b) > cosine(a, c)


async def test_fake_embedding_is_deterministic():
    embedder = FakeEmbeddingService()
    v1 = await embedder.embed_query("revenue")
    v2 = await embedder.embed_query("revenue")
    assert v1 == v2


def test_huggingface_service_does_not_load_model_at_construction():
    """The model must be lazy — constructing the service (which happens at
    import time via the factory in some code paths) must never trigger a
    multi-hundred-MB download."""
    service = HuggingFaceEmbeddingService(model_name="BAAI/bge-small-en-v1.5")
    assert service._model is None
