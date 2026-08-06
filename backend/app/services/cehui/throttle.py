"""自动重规划节流器 — 防止连续追问并发触发多个 AOO 任务互相覆盖

P0 修复背景:
    前端 triggerAutoOptimize 在每次 needs_optimization=true 时直接投递 Celery 任务。
    用户连续追问 5 次就会并发 5 个 AOO 优化，彼此覆盖学习路径，
    既浪费算力又导致路径抖动。

实现: Redis SET NX EX 分布式锁（跨进程/跨 worker 有效）。
     Redis 不可用时**降级放行**（fail-open），不阻断主业务。
"""

from __future__ import annotations

import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_KEY_TMPL = "aoo:auto_optimize:cooldown:{student_id}"


async def acquire_optimize_slot(
    student_id: str,
    cooldown: Optional[int] = None,
) -> tuple[bool, int]:
    """尝试获取自动优化名额

    Returns:
        (acquired, retry_after_seconds)
        acquired=True  → 可以触发 AOO
        acquired=False → 处于冷却窗口内，retry_after 为剩余秒数
    """
    ttl = int(cooldown if cooldown is not None else settings.CHAT_AUTO_OPTIMIZE_COOLDOWN)
    if ttl <= 0:
        return True, 0

    key = _KEY_TMPL.format(student_id=student_id)

    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            ok = await client.set(key, "1", nx=True, ex=ttl)
            if ok:
                return True, 0
            remaining = await client.ttl(key)
            return False, max(0, int(remaining or 0))
        finally:
            await client.aclose()
    except Exception as exc:  # noqa: BLE001
        # Redis 不可用 → 放行，不因为节流器故障阻断核心功能
        logger.warning("[throttle] Redis 不可用，自动优化节流降级放行: %s", exc)
        return True, 0


async def release_optimize_slot(student_id: str) -> None:
    """主动释放名额（任务投递失败时调用，避免白白占用冷却窗口）"""
    key = _KEY_TMPL.format(student_id=student_id)
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            await client.delete(key)
        finally:
            await client.aclose()
    except Exception:  # noqa: BLE001
        pass
