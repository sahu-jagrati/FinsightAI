#!/usr/bin/env bash
# Shared container entrypoint for both the API and worker images.
#
# Runs pending Alembic migrations before starting the actual process, so a
# `docker compose up` never leaves the schema out of date. Migrations are
# idempotent (alembic tracks applied revisions) so this is safe to run from
# every replica on every boot.
set -euo pipefail

echo "[entrypoint] waiting for database to accept connections..."
python -c "
import asyncio
import sys
import time

from sqlalchemy import text
from app.db.session import engine

async def wait():
    for attempt in range(30):
        try:
            async with engine.connect() as conn:
                await conn.execute(text('SELECT 1'))
            return
        except Exception as exc:
            print(f'[entrypoint] db not ready (attempt {attempt + 1}/30): {exc}')
            time.sleep(2)
    sys.exit('[entrypoint] database never became ready')

asyncio.run(wait())
"

echo "[entrypoint] running alembic migrations..."
alembic upgrade head

echo "[entrypoint] starting: $*"
exec "$@"
