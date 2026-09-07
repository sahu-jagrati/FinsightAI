"""Health check endpoint.

`GET /api/health` reports the status of every hard dependency (Postgres,
Redis) so it can back both the admin/system-monitoring page (Section 26)
and container orchestration liveness/readiness probes.
"""

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.core.redis import ping_redis
from app.db.session import AsyncSessionLocal
from app.schemas.health import ComponentHealth, HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    components: list[ComponentHealth] = []

    # --- Postgres ---
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        components.append(ComponentHealth(name="postgresql", status="ok"))
    except Exception as exc:  # noqa: BLE001 - surface any failure as health detail
        components.append(
            ComponentHealth(name="postgresql", status="error", detail=str(exc))
        )

    # --- Redis ---
    if await ping_redis():
        components.append(ComponentHealth(name="redis", status="ok"))
    else:
        components.append(
            ComponentHealth(name="redis", status="error", detail="ping failed")
        )

    overall = "ok" if all(c.status == "ok" for c in components) else "degraded"

    return HealthResponse(
        status=overall,
        app_name=settings.APP_NAME,
        env=settings.ENV,
        components=components,
    )
