from app.services import cache_service


class _BoomRedis:
    """Simulates Redis being unreachable (Section 32)."""

    async def get(self, *a, **kw):
        raise ConnectionError("redis unavailable")

    async def set(self, *a, **kw):
        raise ConnectionError("redis unavailable")

    async def mget(self, *a, **kw):
        raise ConnectionError("redis unavailable")


async def test_cache_get_json_degrades_to_miss_when_redis_down(monkeypatch):
    monkeypatch.setattr(cache_service, "get_redis_client", lambda: _BoomRedis())
    result = await cache_service.cache_get_json("some:key")
    assert result is None


async def test_cache_set_json_never_raises_when_redis_down(monkeypatch):
    monkeypatch.setattr(cache_service, "get_redis_client", lambda: _BoomRedis())
    await cache_service.cache_set_json("some:key", {"a": 1})  # must not raise


async def test_get_cache_stats_degrades_when_redis_down(monkeypatch):
    monkeypatch.setattr(cache_service, "get_redis_client", lambda: _BoomRedis())
    stats = await cache_service.get_cache_stats()
    assert stats == {"hits": 0, "misses": 0, "hit_rate": 0.0}


def test_make_cache_key_is_deterministic():
    k1 = cache_service.make_cache_key("retrieval", "apple revenue", ["Apple"], [2025])
    k2 = cache_service.make_cache_key("retrieval", "apple revenue", ["Apple"], [2025])
    k3 = cache_service.make_cache_key("retrieval", "apple revenue", ["Apple"], [2024])
    assert k1 == k2
    assert k1 != k3
    assert k1.startswith("retrieval:")
