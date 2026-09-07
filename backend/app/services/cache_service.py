"""Redis-backed caching helpers (Section 17).

Generic JSON get/set plus a running hit/miss counter so the admin
dashboard (Section 26) can show a real cache hit ratio, not a hardcoded
number. Cache KEYS follow the `query:{hash}` / `retrieval:{query_hash}`
convention from Section 17.
"""

import hashlib
import json
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis_client

logger = get_logger("cache")

CACHE_STATS_HITS_KEY = "stats:cache:hits"
CACHE_STATS_MISSES_KEY = "stats:cache:misses"


def make_cache_key(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(p) for p in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


async def cache_get_json(key: str) -> Any | None:
    """Never raises — a Redis outage (Section 32) degrades to "always a
    cache miss", not a failed request. Every caller of this treats `None`
    as "go compute it fresh", so that degradation is transparent."""
    try:
        redis = get_redis_client()
        raw = await redis.get(key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cache.get_failed", key=key, error=str(exc))
        return None

    try:
        if raw is None:
            await redis.incr(CACHE_STATS_MISSES_KEY)
            return None
        await redis.incr(CACHE_STATS_HITS_KEY)
    except Exception:  # noqa: BLE001 - stats are best-effort
        pass

    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


async def cache_set_json(key: str, value: Any, ttl_seconds: int | None = None) -> None:
    ttl = ttl_seconds if ttl_seconds is not None else settings.REDIS_CACHE_TTL_SECONDS
    try:
        redis = get_redis_client()
        await redis.set(key, json.dumps(value), ex=ttl)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cache.set_failed", key=key, error=str(exc))


async def get_cache_stats() -> dict[str, int | float]:
    try:
        redis = get_redis_client()
        hits_raw, misses_raw = await redis.mget([CACHE_STATS_HITS_KEY, CACHE_STATS_MISSES_KEY])
    except Exception:  # noqa: BLE001
        return {"hits": 0, "misses": 0, "hit_rate": 0.0}

    hits = int(hits_raw or 0)
    misses = int(misses_raw or 0)
    total = hits + misses
    return {
        "hits": hits,
        "misses": misses,
        "hit_rate": round(hits / total, 4) if total else 0.0,
    }
