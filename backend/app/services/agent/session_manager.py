"""Redis 会话管理器 — 维护 Agent 对话上下文

职责：
1. session_id ↔ 用户 ID 映射
2. 对话历史消息存储（最近 N 条）
3. 会话过期管理（TTL + 自动续期）
4. 用户会话列表查询

Redis Key 设计：
    agent:session:{session_id}:meta      — Hash: user_id, created_at, msg_count, model
    agent:session:{session_id}:messages  — List: 对话消息 (JSON 序列化)
    agent:user:{user_id}:sessions        — Set: 用户的 session_id 集合
    agent:session:ttl                     — 默认 TTL (秒)

用法示例:
    from app.services.agent.session_manager import SessionManager
    mgr = SessionManager()
    await mgr.create_session("sess_1", "user_1")
    await mgr.append_message("sess_1", {"role": "user", "content": "你好"})
    history = await mgr.get_history("sess_1")
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)


# Redis Key 模板
KEY_SESSION_META = "agent:session:{session_id}:meta"
KEY_SESSION_MESSAGES = "agent:session:{session_id}:messages"
KEY_USER_SESSIONS = "agent:user:{user_id}:sessions"

# 默认参数
DEFAULT_TTL = 3600           # 1 小时
DEFAULT_MAX_MESSAGES = 50    # 每个会话最多保留的消息数
RECENT_N_MESSAGES = 20       # 返回给 Agent 的最近消息数


class SessionManager:
    """基于 Redis 的 Agent 会话管理器。

    特性：
    - 异步 Redis 客户端
    - 对话历史自动裁剪
    - TTL 会话过期 + 自动续期
    - 批量操作（Pipeline）
    """

    def __init__(self, ttl: int = DEFAULT_TTL, max_messages: int = DEFAULT_MAX_MESSAGES):
        self._ttl = ttl
        self._max_messages = max_messages
        self._redis: Optional[aioredis.Redis] = None
        logger.info(
            "SessionManager initialized | ttl=%ds | max_messages=%d",
            self._ttl,
            self._max_messages,
        )

    @property
    def ttl(self) -> int:
        return self._ttl

    # ---- Redis 连接 ----

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            # 显式设置 max_connections 防止连接泄漏时无限增长；
            # from_url 内部创建连接池, close() 会释放。调用方应在
            # 应用关闭时调用 SessionManager.close() 回收连接池。
            self._redis = aioredis.Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                max_connections=settings.redis_max_connections,
            )
            logger.debug("SessionManager Redis connection created")
        return self._redis

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.close()
            self._redis = None
            logger.debug("SessionManager Redis connection closed")

    # ---- 会话创建 ----

    async def create_session(
        self,
        session_id: str,
        user_id: str,
        model: str = "xingchen-agent",
        ttl: Optional[int] = None,
    ) -> bool:
        """创建新会话。

        Args:
            session_id: 会话 ID（由前端生成）
            user_id: 用户 ID
            model: 模型标识（可选）
            ttl: 自定义 TTL，默认使用实例默认值

        Returns:
            True 表示新建，False 表示已存在
        """
        redis = await self._get_redis()
        _ttl = ttl or self._ttl
        meta_key = KEY_SESSION_META.format(session_id=session_id)

        # 检查是否已存在
        exists = await redis.exists(meta_key)
        now = datetime.now(tz=timezone.utc)

        meta = {
            "user_id": user_id,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "message_count": "0",
            "model": model,
        }

        async with redis.pipeline(transaction=True) as pipe:
            pipe.hset(meta_key, mapping=meta)
            pipe.expire(meta_key, _ttl)
            # 关联到用户
            user_key = KEY_USER_SESSIONS.format(user_id=user_id)
            pipe.sadd(user_key, session_id)
            pipe.expire(user_key, _ttl * 2)  # 用户集合 TTL 更长
            await pipe.execute()

        if exists:
            logger.debug("Session %s already exists, metadata refreshed", session_id)
        else:
            logger.info("Session created: %s (user=%s)", session_id, user_id)

        return not bool(exists)

    # ---- 消息管理 ----

    async def append_message(
        self,
        session_id: str,
        message: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> int:
        """追加一条消息到对话历史。

        Args:
            session_id: 会话 ID
            message: 消息字典 {"role": "user/assistant/tool", "content": "...", ...}
            user_id: 可选，用于更新 user-sessions 关联
        Returns:
            当前消息总数
        """
        redis = await self._get_redis()
        msg_key = KEY_SESSION_MESSAGES.format(session_id=session_id)
        meta_key = KEY_SESSION_META.format(session_id=session_id)

        # 添加时间戳
        msg_copy = dict(message)
        if "timestamp" not in msg_copy:
            msg_copy["timestamp"] = datetime.now(tz=timezone.utc).isoformat()

        msg_json = json.dumps(msg_copy, ensure_ascii=False)
        now = datetime.now(tz=timezone.utc)

        async with redis.pipeline(transaction=True) as pipe:
            # RPUSH 追加消息
            pipe.rpush(msg_key, msg_json)
            # 裁剪到 max_messages
            pipe.ltrim(msg_key, -self._max_messages, -1)
            # 获取消息总数
            pipe.llen(msg_key)
            # 更新元数据
            pipe.hset(meta_key, mapping={
                "updated_at": now.isoformat(),
                "message_count": "",  # 占位，下面单独更新
            })
            # 续期
            pipe.expire(msg_key, self._ttl)
            pipe.expire(meta_key, self._ttl)

            results = await pipe.execute()

        msg_count = results[2]  # llen 的结果

        # 更新 message_count（因为 pipeline 中不能引用前一个结果）
        await redis.hset(meta_key, "message_count", str(msg_count))

        logger.debug(
            "Appended message to %s | role=%s | total=%d",
            session_id,
            msg_copy.get("role", "?"),
            msg_count,
        )
        return msg_count

    async def get_history(
        self,
        session_id: str,
        limit: int = RECENT_N_MESSAGES,
    ) -> List[Dict[str, Any]]:
        """获取会话的最近 N 条对话历史。

        Args:
            session_id: 会话 ID
            limit: 返回最近几条消息

        Returns:
            消息列表，按时间正序排列
        """
        redis = await self._get_redis()
        msg_key = KEY_SESSION_MESSAGES.format(session_id=session_id)

        # LRANGE 取最后 limit 条
        raw_messages = await redis.lrange(msg_key, -limit, -1)

        messages: List[Dict[str, Any]] = []
        for raw in raw_messages:
            try:
                messages.append(json.loads(raw))
            except json.JSONDecodeError:
                logger.warning("Session %s: invalid JSON in message history", session_id)
                continue

        return messages

    async def get_messages_for_agent(
        self,
        session_id: str,
        system_prompt: Optional[str] = None,
        limit: int = RECENT_N_MESSAGES,
    ) -> List[Dict[str, Any]]:
        """获取格式化为 Agent API 可用的消息列表。

        Args:
            session_id: 会话 ID
            system_prompt: 可选的系统提示词（添加到最前面）
            limit: 返回最近几条消息

        Returns:
            消息列表，格式: [{"role": "system/user/assistant/tool", "content": "..."}]
        """
        history = await self.get_history(session_id, limit=limit)

        # 提取 role + content，过滤掉内部字段
        messages: List[Dict[str, Any]] = []
        for h in history:
            msg: Dict[str, Any] = {"role": h.get("role", "user")}
            if "content" in h:
                msg["content"] = h["content"]
            if h.get("tool_calls"):
                msg["tool_calls"] = h["tool_calls"]
            if h.get("tool_call_id"):
                msg["tool_call_id"] = h["tool_call_id"]
            if h.get("name"):
                msg["name"] = h["name"]
            messages.append(msg)

        # 注入 system prompt
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})

        return messages

    # ---- 会话查询 ----

    async def get_meta(self, session_id: str) -> Optional[Dict[str, str]]:
        """获取会话元数据"""
        redis = await self._get_redis()
        meta_key = KEY_SESSION_META.format(session_id=session_id)
        meta = await redis.hgetall(meta_key)
        return meta if meta else None

    async def get_user_sessions(self, user_id: str) -> List[str]:
        """获取用户的所有会话 ID 列表"""
        redis = await self._get_redis()
        user_key = KEY_USER_SESSIONS.format(user_id=user_id)
        sessions = await redis.smembers(user_key)
        return list(sessions)

    async def get_user_sessions_detail(
        self,
        user_id: str,
    ) -> List[Dict[str, Any]]:
        """获取用户所有会话的详细信息

        用 pipeline 批量拉取每个会话的元数据与 TTL，避免 N 个会话触发 N+1 次
        Redis 往返（smembers 1 次 + 每会话 hgetall + ttl 各 1 次）。
        """
        session_ids = await self.get_user_sessions(user_id)
        if not session_ids:
            return []

        redis = await self._get_redis()
        # 收集每个会话的 meta_key，按顺序批量发起 hgetall / ttl
        meta_keys = [KEY_SESSION_META.format(session_id=sid) for sid in session_ids]
        async with redis.pipeline(transaction=False) as pipe:
            for mk in meta_keys:
                pipe.hgetall(mk)
            for mk in meta_keys:
                pipe.ttl(mk)
            responses = await pipe.execute()

        # 前半段是各会话的 hgetall，后半段是对应的 ttl
        metas = responses[: len(session_ids)]
        ttls = responses[len(session_ids):]

        result = []
        for sid, meta, ttl in zip(session_ids, metas, ttls):
            if meta:
                meta = dict(meta)
                meta["session_id"] = sid
                meta["ttl_seconds"] = ttl if isinstance(ttl, int) and ttl > 0 else 0
                meta["message_count"] = int(meta.get("message_count", "0"))
                result.append(meta)

        # 按最近活跃时间降序
        result.sort(key=lambda m: m.get("updated_at", ""), reverse=True)
        return result

    # ---- 会话生命周期 ----

    async def renew_session(self, session_id: str, ttl: Optional[int] = None) -> bool:
        """续期会话 TTL"""
        redis = await self._get_redis()
        _ttl = ttl or self._ttl
        meta_key = KEY_SESSION_META.format(session_id=session_id)
        msg_key = KEY_SESSION_MESSAGES.format(session_id=session_id)

        async with redis.pipeline(transaction=True) as pipe:
            pipe.expire(meta_key, _ttl)
            pipe.expire(msg_key, _ttl)
            pipe.hset(meta_key, "updated_at", datetime.now(tz=timezone.utc).isoformat())
            await pipe.execute()

        logger.debug("Session %s TTL renewed to %ds", session_id, _ttl)
        return True

    async def delete_session(self, session_id: str) -> bool:
        """删除会话及其所有数据"""
        redis = await self._get_redis()
        meta_key = KEY_SESSION_META.format(session_id=session_id)
        msg_key = KEY_SESSION_MESSAGES.format(session_id=session_id)

        # 获取 user_id 以清理关联
        meta = await redis.hgetall(meta_key)
        user_id = meta.get("user_id", "")

        async with redis.pipeline(transaction=True) as pipe:
            pipe.delete(meta_key, msg_key)
            if user_id:
                user_key = KEY_USER_SESSIONS.format(user_id=user_id)
                pipe.srem(user_key, session_id)
            await pipe.execute()

        logger.info("Session deleted: %s", session_id)
        return True

    async def clear_all_user_sessions(self, user_id: str) -> int:
        """清除用户的所有会话

        批量删除: 收集会话 key 后用 pipeline 一次性 unlink (异步删除,
        不阻塞主线程) 所有数据, 并单次 srem 从用户集合移除全部 sid,
        避免会话数较多时的串行 N 次往返 (建议100)。
        """
        sessions = await self.get_user_sessions(user_id)
        if not sessions:
            return 0

        redis = await self._get_redis()
        user_key = KEY_USER_SESSIONS.format(user_id=user_id)
        async with redis.pipeline(transaction=False) as pipe:
            for sid in sessions:
                meta_key = KEY_SESSION_META.format(session_id=sid)
                msg_key = KEY_SESSION_MESSAGES.format(session_id=sid)
                pipe.unlink(meta_key, msg_key)
            pipe.srem(user_key, *sessions)
            await pipe.execute()

        logger.info("All sessions cleared for user %s | count=%d", user_id, len(sessions))
        return len(sessions)

    # ---- 健康检查 ----

    async def ping(self) -> bool:
        """Redis 连通性检查"""
        try:
            redis = await self._get_redis()
            return await redis.ping()
        except Exception:
            return False


# ============================================================================
# 全局单例
# ============================================================================

_session_manager_instance: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """获取 SessionManager 全局单例"""
    global _session_manager_instance

    if _session_manager_instance is None:
        _session_manager_instance = SessionManager(
            ttl=settings.XINGCHEN_SESSION_TTL,
        )
        logger.info("SessionManager global singleton created")

    return _session_manager_instance
