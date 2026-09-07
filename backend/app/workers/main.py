"""Background worker process entrypoint.

Section 18 requires the API layer and worker layer to be separate processes
so expensive work (PDF parsing, embedding generation, indexing, long-running
agent workflows) never blocks an HTTP request.

Phase 1 shipped this as an idle heartbeat proving the process boots and can
reach Postgres + Redis. Phase 2 replaces the loop body with a real
consumer: it blocks on the Redis ingestion queue (`app/services/job_queue`)
and runs each document through `app/rag/ingestion/pipeline.process_document`.

Run locally with:
    python -m app.workers.main

Run in Docker via `docker compose up worker`.
"""

import asyncio
import signal

from sqlalchemy import text

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.redis import get_redis_client
from app.db.session import AsyncSessionLocal
from app.rag.ingestion.pipeline import process_document
from app.services.job_queue import dequeue_ingestion_job

configure_logging()
logger = get_logger("worker")

POLL_INTERVAL_SECONDS = 5


async def _check_dependencies() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))
    redis_client = get_redis_client()
    await redis_client.ping()


async def main() -> None:
    logger.info("worker.starting", env=settings.ENV)
    await _check_dependencies()
    logger.info("worker.ready", queue="queue:ingestion")

    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # add_signal_handler is unsupported on Windows' default loop.
            pass

    while not stop_event.is_set():
        job = await dequeue_ingestion_job(timeout_seconds=POLL_INTERVAL_SECONDS)
        if job is None:
            continue  # timed out waiting — loop back and check stop_event

        logger.info("worker.job_received", document_id=str(job.document_id))
        try:
            await process_document(job.document_id)
        except Exception:  # noqa: BLE001 - a bad job must never kill the worker
            logger.exception("worker.job_crashed", document_id=str(job.document_id))

    logger.info("worker.stopped")


if __name__ == "__main__":
    asyncio.run(main())
