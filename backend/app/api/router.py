"""Top-level API router. Each domain's routes live in `app/api/routes/*` and
are included here — new endpoint groups (documents, query, analyze,
companies, metrics...) are wired in as later phases add them.
"""

from fastapi import APIRouter

from app.api.routes import analysis, companies, dashboard, documents, health, metrics

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(documents.router)
api_router.include_router(companies.router)
api_router.include_router(analysis.router)
api_router.include_router(metrics.router)
api_router.include_router(dashboard.router)
