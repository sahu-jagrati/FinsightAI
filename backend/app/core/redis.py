"""Async Redis client (single shared connection pool per event loop).

Used across the app for (Section 17): query/retrieval/LLM response caching,
session state, background task status, and rate limiting. A single module
keeps the connection pool centralized instead of every service opening its
own client.
"""

import asyncio
from collections.abc import AsyncGenerator

import redis.asyncio as redis

from app.core.config import settings

_redis_pool: redis.ConnectionPool | None = None
_pool_loop: asyncio.AbstractEventLoop | None = None


def _get_pool() -> redis.ConnectionPool:
    """Returns the shared connection pool, recreating it if the running
    event loop has changed since it was built.

    `redis.asyncio.ConnectionPool` holds asyncio-loop-bound primitives
    internally, so reusing one pool across two different event loops
    breaks unpredictably. A single long-lived process only ever has one
    loop, so this is a no-op there — it exists for anything that legitimately
    runs multiple loops over the process's lifetime, most notably a test
    suite where pytest-asyncio gives each test function its own loop.
    """
    global _redis_pool, _pool_loop

    current_loop = asyncio.get_running_loop()
    if _redis_pool is None or _pool_loop is not current_loop:
        _redis_pool = redis.ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=50,
            # Fail fast when Redis is unreachable at all (Section 32) —
            # every caller here treats a connection error as "degrade
            # gracefully", which only works well if that error arrives
            # quickly. Deliberately NOT setting `socket_timeout` (the
            # per-read timeout): blocking commands like BLPOP (see
            # job_queue.py) legitimately hold the socket open for their
            # whole `timeout=N` argument, and a blanket read timeout
            # shorter than that raises a spurious
            # `redis.exceptions.TimeoutError` instead of the command's own
            # well-defined "nothing arrived in time" result.
            socket_connect_timeout=1.0,
        )
        _pool_loop = current_loop

    return _redis_pool


def get_redis_client() -> redis.Redis:
    """Return a Redis client bound to the shared connection pool.

    Cheap to call repeatedly — the underlying pool is reused, not recreated
    (unless the event loop changed — see `_get_pool`).
    """
    return redis.Redis(connection_pool=_get_pool())


async def get_redis() -> AsyncGenerator[redis.Redis, None]:
    """FastAPI dependency variant of `get_redis_client`."""
    client = get_redis_client()
    try:
        yield client
    finally:
        await client.aclose()


async def ping_redis() -> bool:
    try:
        client = get_redis_client()
        return await client.ping()
    except Exception:
        return False
