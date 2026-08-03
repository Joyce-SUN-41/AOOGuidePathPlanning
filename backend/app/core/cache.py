"""轻量级 Redis 查询缓存封装。

设计原则（与现有 aoo_optimization / session_manager 一致）：
- 复用官方 ``redis`` 库的异步客户端（requirements 中已声明 redis>=5）。
- **可降级**：Redis 不可用 / 未配置 / 序列化失败 时，所有方法静默返回 None，
  调用方应直接回退到数据库查询，绝不影响现有业务功能。
- 统一的 JSON 序列化（业务数据均为可 JSON 化的 dict / list）。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# 模块级连接池，避免每次请求新建连接
_pool = None


def _get_redis():
    """返回 Redis 异步客户端；不可用（未配置 URL 或导入失败）时返回 None。"""
    redis_url = settings.redis_url
    if not redis_url:
        return None
    global _pool
    try:
        import redis.asyncio as aioredis

        if _pool is None:
            _pool = aioredis.ConnectionPool.from_url(
                redis_url,
                decode_responses=True,
                max_connections=8,
            )
        return aioredis.Redis(connection_pool=_pool)
    except Exception as e:  # noqa: BLE001 — 缓存层故障不应影响主流程
        logger.warning("[cache] Redis 不可用，降级为直查: %s", e)
        return None


async def cache_get(key: str) -> Optional[Any]:
    """读取缓存；未命中或失败时返回 None。"""
    r = _get_redis()
    if r is None:
        return None
    try:
        raw = await r.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:  # noqa: BLE001
        logger.warning("[cache] 读取失败，降级为直查: %s", e)
        return None


async def cache_set(key: str, value: Any, ttl: int = 300) -> None:
    """写入缓存；失败静默忽略。ttl 单位秒。"""
    r = _get_redis()
    if r is None:
        return
    try:
        await r.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
    except Exception as e:  # noqa: BLE001
        logger.warning("[cache] 写入失败，已忽略: %s", e)


async def cache_delete(key: str) -> None:
    """删除缓存；失败静默忽略。"""
    r = _get_redis()
    if r is None:
        return
    try:
        await r.delete(key)
    except Exception as e:  # noqa: BLE001
        logger.warning("[cache] 删除失败，已忽略: %s", e)
