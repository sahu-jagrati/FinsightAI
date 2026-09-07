"""Redis-backed background job queue (Section 17/18).

Deliberately simple — a Redis list used as a FIFO via RPUSH/BLPOP — rather
than pulling in Celery/arq. That's the right trade-off for this project: a
single job type (process an uploaded document) with at-least-once delivery
and no need for scheduling, retries-with-backoff, or multi-queue routing.
Task status lives in a Redis hash so the API can answer "how's my upload
doing?" without polling Postgres.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.core.redis import get_redis_client

INGESTION_QUEUE_KEY = "queue:ingestion"
TASK_STATUS_KEY_PREFIX = "task:ingestion:"
TASK_STATUS_TTL_SECONDS = 60 * 60 * 24  # 1 day — enough to show recent history


class TaskState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IngestionJob:
    document_id: uuid.UUID
    enqueued_at: str


async def enqueue_ingestion_job(document_id: uuid.UUID) -> None:
    redis = get_redis_client()
    payload = {
        "document_id": str(document_id),
        "enqueued_at": datetime.now(UTC).isoformat(),
    }
    await redis.rpush(INGESTION_QUEUE_KEY, json.dumps(payload))
    await set_task_status(document_id, TaskState.QUEUED)


async def dequeue_ingestion_job(timeout_seconds: int = 5) -> IngestionJob | None:
    """Blocking pop with a timeout so the worker loop can still check for
    shutdown signals between polls instead of blocking forever."""
    redis = get_redis_client()
    result = await redis.blpop([INGESTION_QUEUE_KEY], timeout=timeout_seconds)
    if result is None:
        return None
    _key, raw = result
    payload = json.loads(raw)
    return IngestionJob(
        document_id=uuid.UUID(payload["document_id"]),
        enqueued_at=payload["enqueued_at"],
    )


async def set_task_status(
    document_id: uuid.UUID,
    state: TaskState,
    *,
    stage: str | None = None,
    detail: str | None = None,
) -> None:
    redis = get_redis_client()
    key = f"{TASK_STATUS_KEY_PREFIX}{document_id}"
    mapping = {
        "state": state.value,
        "stage": stage or "",
        "detail": detail or "",
        "updated_at": datetime.now(UTC).isoformat(),
    }
    await redis.hset(key, mapping=mapping)
    await redis.expire(key, TASK_STATUS_TTL_SECONDS)


async def get_task_status(document_id: uuid.UUID) -> dict[str, str] | None:
    redis = get_redis_client()
    key = f"{TASK_STATUS_KEY_PREFIX}{document_id}"
    data = await redis.hgetall(key)
    return data or None
