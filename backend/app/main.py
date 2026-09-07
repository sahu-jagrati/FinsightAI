"""FastAPI application entrypoint.

Run locally with:
    uvicorn app.main:app --reload

Run in Docker via `docker compose up backend`.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging, get_logger
from app.core.rate_limit import RateLimitMiddleware

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "startup",
        app_name=settings.APP_NAME,
        env=settings.ENV,
        llm_provider=settings.LLM_PROVIDER,
    )
    yield
    logger.info("shutdown")


app = FastAPI(
    title=settings.APP_NAME,
    description="Autonomous Multi-Agent Agentic RAG Engine for Financial Analytics",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Turns every domain error (Section 32) into a consistent
    `{"error": {"code", "message"}}` body the frontend can branch on,
    instead of a generic 500."""
    logger.warning("app_error", code=exc.code, message=exc.message, path=request.url.path)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.get("/", tags=["root"])
async def root() -> dict:
    return {
        "name": settings.APP_NAME,
        "tagline": "Your autonomous AI financial research analyst.",
        "docs": "/api/docs",
        "health": f"{settings.API_V1_PREFIX}/health",
    }
