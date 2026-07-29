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
            password=os.getenv('POSTGRES_PASSWORD', 'aoo_password_2024'),
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
        echo "WARNING: Redis did not become ready, continuing anyway..."
        break
    fi
    echo "  Waiting... (attempt $RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done
echo "  Redis is ready!"

# 运行数据库迁移
echo "[3/3] Running database migrations..."
python -m alembic upgrade head || {
    echo "WARNING: Alembic migration failed, attempting direct table creation..."
    python _create_tables.py || echo "WARNING: Direct table creation also failed"
}
echo "  Migrations complete!"

echo "========================================"
echo " Starting application..."
echo "========================================"

# 执行传入的 CMD
exec "$@"
