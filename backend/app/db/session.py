"""Async SQLAlchemy engine + session factory.

The engine uses a connection pool sized from settings (Section 18/31:
connection pooling is required for the API to stay responsive under
concurrent agent/retrieval workloads). `get_db` is the FastAPI dependency
every route/service uses to obtain a session; it guarantees the session is
closed (and rolled back on error) at the end of the request.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a request-scoped async session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """FastAPI dependency handing out the session *factory* itself, not a
    session. A single `AsyncSession` can't be used from concurrent
    coroutines (SQLAlchemy raises `IllegalStateChangeError`), so code that
    needs genuine concurrent DB reads — the Retrieval Agent's per-company
    hybrid search (Section 31) — opens one short-lived session per
    concurrent branch from this factory instead of sharing the
    request-scoped `db` session across `asyncio.gather`. Overridden in
    tests the same way `get_db` is, so it points at the test database."""
    return AsyncSessionLocal


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for use outside of FastAPI requests (workers, scripts)."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
