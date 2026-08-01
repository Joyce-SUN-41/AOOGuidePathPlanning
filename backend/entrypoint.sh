#!/bin/bash
set -e

echo "========================================"
echo " AOO Backend Entrypoint"
echo "========================================"

# 等待 PostgreSQL 就绪
echo "[1/3] Waiting for PostgreSQL..."
MAX_RETRIES=30
RETRY_COUNT=0
until python -c "
import asyncpg, os, asyncio

async def check():
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'postgres'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'aoo_user'),
            password=os.getenv('POSTGRES_PASSWORD', 'changeme'),
            database=os.getenv('POSTGRES_DB', 'aoo_guide_path'),
            timeout=5
        )
        await conn.close()
        return True
    except Exception:
        return False

print('OK' if asyncio.run(check()) else 'FAIL')
" 2>/dev/null; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo "ERROR: PostgreSQL did not become ready in time"
        exit 1
    fi
    echo "  Waiting... (attempt $RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done
echo "  PostgreSQL is ready!"

# 等待 Redis 就绪
echo "[2/3] Waiting for Redis..."
RETRY_COUNT=0
until python -c "
import redis, os
try:
    r = redis.from_url(os.getenv('REDIS_URL', os.getenv('CELERY_BROKER_URL', 'redis://redis:6379/0')))
    r.ping()
    print('OK')
except Exception:
    print('FAIL')
" 2>/dev/null; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo "ERROR: Redis did not become ready in time"
        exit 1
    fi
    echo "  Waiting... (attempt $RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done
echo "  Redis is ready!"

# 运行数据库迁移
echo "[3/3] Running database migrations..."
# --- 修复 alembic_version 表列宽 (迁移 ID 超过 32 字符) ---
echo "  Fixing alembic_version column width if needed..."
python -c "
import asyncio, os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
DB_URL = os.getenv('DATABASE_URL', 'postgresql+asyncpg://aoo_user:changeme@postgres:5432/aoo_guide_path')
async def fix():
    engine = create_async_engine(DB_URL)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text(
                \"SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public' AND tablename='alembic_version'\"
            ))
            if result.fetchone():
                await conn.execute(text('ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)'))
                print('  alembic_version.version_num widened to VARCHAR(64)')
            else:
                print('  alembic_version table not found, skipping')
    except Exception as e:
        print(f'  Column fix skipped: {e}')
    finally:
        await engine.dispose()
asyncio.run(fix())
"

python -m alembic upgrade head || {
    echo "WARNING: Alembic migration failed, checking if tables already exist..."
    python -c "
import asyncio, os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

DB_URL = os.getenv('DATABASE_URL', 'postgresql+asyncpg://aoo_user:changeme@postgres:5432/aoo_guide_path')

async def check():
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(text(\"SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public'\"))
        tables = [row[0] for row in result.fetchall()]
        if 'users' in tables:
            print(f'Found {len(tables)} existing tables, stamping alembic head...')
            await conn.close()
            return True
        await conn.close()
        return False

if asyncio.run(check()):
    exit(0)
else:
    exit(1)
" && python -m alembic stamp head && echo "  Existing tables detected, stamped head." || {
    echo "ERROR: Migration failed and no existing tables found, cannot start"
    exit 1
}
}
echo "  Migrations complete!"

echo "========================================"
echo " Starting application..."
echo "========================================"

# 执行传入的 CMD
exec "$@"
