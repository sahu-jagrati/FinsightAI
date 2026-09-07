#!/usr/bin/env bash
# Worker entrypoint: waits for Postgres/Redis but does NOT run migrations
# itself — the API container's entrypoint.sh owns schema migrations so two
# containers never race to apply them concurrently at boot.
set -euo pipefail

echo "[entrypoint.worker] waiting for database to accept connections..."
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
            print(f'[entrypoint.worker] db not ready (attempt {attempt + 1}/30): {exc}')
            time.sleep(2)
    sys.exit('[entrypoint.worker] database never became ready')

asyncio.run(wait())
"

echo "[entrypoint.worker] starting: $*"
exec "$@"
