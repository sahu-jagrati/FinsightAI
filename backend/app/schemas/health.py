from pydantic import BaseModel


class ComponentHealth(BaseModel):
    name: str
    status: str  # "ok" | "error" | "not_configured"
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded"
    app_name: str
    env: str
    components: list[ComponentHealth]
