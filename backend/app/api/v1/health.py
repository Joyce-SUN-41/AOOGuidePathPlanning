"""健康检查 & Prometheus 监控端点"""

import platform
import time
from typing import Dict, Any

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter()

_start_time = time.time()


@router.get("/health")
async def health_check():
    """服务健康检查"""
    return {"status": "ok", "message": "AOO Guide Path Planning API is running"}


@router.get("/health/ready")
async def readiness_check():
    """就绪检查 — 检查数据库、Redis 等依赖是否可用"""
    checks: Dict[str, Any] = {
        "status": "ok",
        "uptime_seconds": round(time.time() - _start_time, 1),
        "python_version": platform.python_version(),
        "checks": {},
    }

    # 数据库检查
    try:
        from app.core.database import check_db_connection
        db_ok = await check_db_connection()
        checks["checks"]["database"] = "ok" if db_ok else "unavailable"
        if not db_ok:
            checks["status"] = "degraded"
    except Exception as e:
        checks["checks"]["database"] = f"error: {e}"
        checks["status"] = "degraded"

    # Redis 检查
    try:
        import redis.asyncio as aioredis
        from app.core.config import settings

        r = aioredis.from_url(settings.redis_url)
        await r.ping()
        await r.close()
        checks["checks"]["redis"] = "ok"
    except Exception as e:
        checks["checks"]["redis"] = f"error: {e}"
        checks["status"] = "degraded"

    return checks


@router.get("/health/live")
async def liveness_check():
    """存活检查 — 最轻量，只确认进程活着"""
    return {"status": "alive"}


# ── Prometheus metrics ──────────────────────────────────


@router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    """Prometheus 指标端点（简化版，不依赖 prometheus_client 库）"""
    from app.core.database import AsyncSessionLocal

    metrics_lines = [
        "# HELP app_info Application information",
        "# TYPE app_info gauge",
        f'app_info{{version="1.0.0",python="{platform.python_version()}"}} 1',
        "",
        "# HELP app_uptime_seconds Application uptime in seconds",
        "# TYPE app_uptime_seconds gauge",
        f"app_uptime_seconds {time.time() - _start_time:.2f}",
        "",
    ]

    # 尝试获取数据库连接池状态
    try:
        async with AsyncSessionLocal() as db:
            from sqlalchemy import text
            result = await db.execute(text("SELECT 1"))
            await result.scalar()
            metrics_lines.append("# HELP db_connection_pool_active Database connection pool active")
            metrics_lines.append("# TYPE db_connection_pool_active gauge")
            metrics_lines.append("db_connection_pool_active 1")
            metrics_lines.append("")
    except Exception:
        metrics_lines.append("# HELP db_connection_pool_active Database connection pool active")
        metrics_lines.append("# TYPE db_connection_pool_active gauge")
        metrics_lines.append("db_connection_pool_active 0")
        metrics_lines.append("")

    # 尝试获取 Redis 状态
    try:
        import redis.asyncio as aioredis
        from app.core.config import settings

        r = aioredis.from_url(settings.redis_url)
        await r.ping()
        await r.close()
        metrics_lines.append("# HELP redis_up Redis connection status")
        metrics_lines.append("# TYPE redis_up gauge")
        metrics_lines.append("redis_up 1")
        metrics_lines.append("")
    except Exception:
        metrics_lines.append("# HELP redis_up Redis connection status")
        metrics_lines.append("# TYPE redis_up gauge")
        metrics_lines.append("redis_up 0")
        metrics_lines.append("")

    return PlainTextResponse("\n".join(metrics_lines), media_type="text/plain; version=0.0.4")

