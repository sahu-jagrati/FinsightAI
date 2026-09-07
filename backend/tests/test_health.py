import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "FinSight AI"
    assert body["health"] == "/api/health"


@pytest.mark.asyncio
async def test_health_reports_all_components(client: AsyncClient) -> None:
    """The health endpoint must never 500 — even with no live Postgres/Redis
    it should report per-component status so the admin dashboard (Section 26)
    always gets a usable response."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200

    body = resp.json()
    assert body["status"] in ("ok", "degraded")

    component_names = {c["name"] for c in body["components"]}
    assert component_names == {"postgresql", "redis"}
    for component in body["components"]:
        assert component["status"] in ("ok", "error", "not_configured")
