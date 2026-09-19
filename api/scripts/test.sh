#!/bin/sh
# Run the API test suite against a separate *_test database and Redis db 15.
#   docker compose run --rm api-test            (extra pytest args go at the end, e.g. -k classes)
set -e
TEST_DB="${POSTGRES_DB}_test"
export DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${TEST_DB}"
export REDIS_URL="redis://redis:6379/15"

python - <<EOF
import asyncio, asyncpg
async def main():
    conn = await asyncpg.connect(user="${POSTGRES_USER}", password="${POSTGRES_PASSWORD}", host="postgres", database="${POSTGRES_DB}")
    if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = \$1", "${TEST_DB}"):
        await conn.execute('CREATE DATABASE "${TEST_DB}"')
    await conn.close()
asyncio.run(main())
EOF

alembic upgrade head
pytest "$@"
