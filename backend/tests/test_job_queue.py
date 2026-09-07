"""Requires a real Redis (set REDIS_URL, or run `docker compose up redis`).
Skipped automatically when Redis isn't reachable, mirroring how the health
endpoint degrades rather than requiring infra to be up for the whole suite.
"""

import uuid

import pytest

from app.core.redis import ping_redis
from app.services.job_queue import (
    TaskState,
    dequeue_ingestion_job,
    enqueue_ingestion_job,
    get_task_status,
)


@pytest.fixture(autouse=True)
async def _require_redis():
    if not await ping_redis():
        pytest.skip("Redis is not reachable — start it with `docker compose up redis`.")


@pytest.mark.asyncio
async def test_enqueue_and_dequeue_round_trip():
    document_id = uuid.uuid4()

    await enqueue_ingestion_job(document_id)
    job = await dequeue_ingestion_job(timeout_seconds=2)

    assert job is not None
    assert job.document_id == document_id

    status = await get_task_status(document_id)
    assert status is not None
    assert status["state"] == TaskState.QUEUED.value


@pytest.mark.asyncio
async def test_dequeue_times_out_on_empty_queue():
    job = await dequeue_ingestion_job(timeout_seconds=1)
    assert job is None
