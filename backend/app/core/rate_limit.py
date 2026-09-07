"""Fixed-window rate limiting middleware, backed by Redis (Section 17/27).

Keyed by client IP + the current minute (`ratelimit:{ip}:{unix_minute}`),
incremented with `INCR` and given a 60s TTL on first write — a classic
fixed-window counter. Degrades to "allow the request" if Redis is
unreachable (Section 32): a rate limiter that turns into a hard outage
when its own backing store hiccups is worse than one that occasionally
under-limits.
"""

import time

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis_client

logger = get_logger("rate_limit")


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith(settings.API_V1_PREFIX):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        window = int(time.time() // 60)
        key = f"ratelimit:{client_ip}:{window}"

        try:
            redis = get_redis_client()
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, 60)
        except Exception as exc:  # noqa: BLE001 - Redis outage must not block requests
            logger.warning("rate_limit.redis_unavailable", error=str(exc))
            return await call_next(request)

        if count > settings.REDIS_RATE_LIMIT_PER_MINUTE:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": {
                        "code": "rate_limited",
                        "message": "Too many requests — please slow down and try again shortly.",
                    }
                },
                headers={"Retry-After": "60"},
            )

        return await call_next(request)
