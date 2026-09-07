import pytest
from httpx import AsyncClient

from app.core.redis import ping_redis


async def test_requests_succeed_when_redis_unavailable(client: AsyncClient):
    """Implicitly proven by every other test in the suite too (Redis isn't
    running in this environment), but spelled out explicitly here as the
    behavior Section 32 requires: a rate limiter must never turn a Redis
    outage into blocked traffic."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200


async def test_rate_limit_enforced_when_redis_available(client: AsyncClient, monkeypatch):
    if not await ping_redis():
        pytest.skip("Redis is not reachable — start it with `docker compose up redis`.")

    from app.core.config import settings

    monkeypatch.setattr(settings, "REDIS_RATE_LIMIT_PER_MINUTE", 3)

    statuses = [(await client.get("/api/health")).status_code for _ in range(5)]
    assert 429 in statuses
