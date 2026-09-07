"""Shared pytest fixtures.

`client` gives every test an httpx.AsyncClient wired directly to the FastAPI
app via ASGITransport — no running server/socket needed.

`db_session` / the DB-aware `client` fixture (`client_db`) run against an
in-memory SQLite database (via aiosqlite) rather than a real Postgres —
Section 30 tests should not require standing up infrastructure. Models use
the portable `GUID` type (`app/db/types.py`) specifically so this works.
Real Postgres-only behavior (pgvector similarity search, full-text search)
gets its own integration tests once those land (Phase 3+), skipped unless
`TEST_DATABASE_URL` points at a real Postgres.
"""

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db, get_session_factory
from app.main import app

# Import models so they're registered on Base.metadata before create_all.
from app import models  # noqa: F401


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # `document_chunks` uses Postgres-only types (pgvector's Vector, JSONB)
    # that don't compile against SQLite — it's covered by the Postgres-only
    # fixtures in test_vector_store.py / test_hybrid_search.py instead.
    portable_tables = [
        t for t in Base.metadata.sorted_tables if t.name != "document_chunks"
    ]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=portable_tables)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def client_db(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """An HTTP client whose `get_db` dependency is overridden to use the
    in-memory test database instead of the real Postgres engine."""

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def pg_engine() -> AsyncGenerator:
    """A REAL Postgres engine, for behavior SQLite can't fake: pgvector
    similarity search and Postgres full-text search.

    Opt-in only, via `TEST_DATABASE_URL` — never falls back to the app's
    own `DATABASE_URL`, since this fixture creates and drops every table.
    Point it at a disposable database, e.g.:
        TEST_DATABASE_URL=postgresql+asyncpg://finsight:finsight@localhost:5432/finsight_test
    """
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "TEST_DATABASE_URL not set — skipping Postgres-only test. "
            "Set it to a disposable database to run these."
        )

    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"TEST_DATABASE_URL is not reachable: {exc}")

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    # This fixture gives every test a fresh, empty schema — but if a real
    # Redis is also running, the Retrieval Agent's cross-test-persistent
    # `retrieval:{hash}` cache doesn't know that. Its cache key is query
    # text + company *names* + filters, not row IDs, so two tests asking
    # about "Apple" would otherwise silently share a cached result — one
    # pointing at company/chunk UUIDs from a schema this test never
    # created (and the previous test's schema already dropped), which
    # surfaces as a foreign-key violation instead of a wrong answer. Best
    # effort: if Redis isn't running, there's nothing to invalidate anyway.
    try:
        from app.core.redis import get_redis_client

        await get_redis_client().flushdb()
    except Exception:  # noqa: BLE001
        pass

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_sessionmaker(pg_engine) -> async_sessionmaker[AsyncSession]:
    """The factory itself (not a session) — needed anywhere that opens more
    than one concurrent session against the test database, e.g. the
    Retrieval Agent's per-company sessions (`state.session_factory`)."""
    return async_sessionmaker(bind=pg_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def pg_session(pg_sessionmaker) -> AsyncGenerator[AsyncSession, None]:
    async with pg_sessionmaker() as session:
        yield session


@pytest_asyncio.fixture
async def client_pg(
    pg_session: AsyncSession, pg_sessionmaker
) -> AsyncGenerator[AsyncClient, None]:
    """Like `client_db`, but backed by a real Postgres (`pg_session`) —
    for endpoints (`/api/analyze`, `/api/query`) whose pipeline runs
    Postgres-only SQL (pgvector cosine distance, full-text search) that
    SQLite can't execute at all, not just can't schema-match. Also
    overrides `get_session_factory` so the Retrieval Agent's per-company
    concurrent sessions land on the same test database, not the app's real
    configured one.
    """

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield pg_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_session_factory] = lambda: pg_sessionmaker
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_session_factory, None)
