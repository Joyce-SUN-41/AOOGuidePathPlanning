"""Agent 服务层 — 对话业务编排

编排 Xingchen Agent 客户端 + 会话管理器，
提供：
- 对话处理（流式 + 非流式）
- 会话生命周期管理
- 对话历史格式化
- 工具调用结果提取
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.schemas.agent import (
    AgentChatResponse,
    AgentHistoryItem,
    AgentHistoryResponse,
    AgentSessionInfo,
    AgentSessionListResponse,
    AgentUsage,
    ToolCallResult,
)
from app.services.agent.session_manager import SessionManager, get_session_manager
from app.services.agent.xingchen_client import (
    AgentCircuitOpenError,
    AgentClientError,
    AgentResponse,
    XingchenAgentClient,
    get_agent_client,
)

logger = logging.getLogger(__name__)


# ---- 系统提示词 ----

DEFAULT_SYSTEM_PROMPT = """你是"燕麦智导"学习助手，一个基于AOO优化算法的个性化学习路径推荐系统。

你的核心能力：
1. 学习路径规划：根据学生的诊断结果，推荐最优学习路径
2. 学科知识问答：基于RAG知识库，回答学科专业问题
3. 学习陪伴：提供学习建议、错题归因、复习提醒

工作流程：
1. 当用户请求"生成学习路径"时，调用AOO路径规划工具
2. 当用户提出学科问题时，调用RAG知识库问答工具
3. 当用户询问学习建议时，基于诊断数据生成个性化建议

回复风格：亲切、专业、有教育温度"""


class AgentService:
    """Agent 对话服务。

    编排 Agent 客户端 + 会话管理器，提供统一的对话接口。
    """

    def __init__(
        self,
        client: Optional[XingchenAgentClient] = None,
        session_mgr: Optional[SessionManager] = None,
    ):
        self._client = client
        self._session_mgr = session_mgr
        self._system_prompt = DEFAULT_SYSTEM_PROMPT

    @property
    def client(self) -> XingchenAgentClient:
        if self._client is None:
            self._client = get_agent_client()
        return self._client

    @property
    def session_mgr(self) -> SessionManager:
        if self._session_mgr is None:
            self._session_mgr = get_session_manager()
        return self._session_mgr

    @property
    def is_configured(self) -> bool:
        return self.client.is_configured

    # ---- 对话 ----

    async def chat(
        self,
        session_id: str,
        message: str,
        user_id: str,
    ) -> AgentChatResponse:
        """非流式对话 — 完整响应一次性返回。

        Args:
            session_id: 会话 ID
            message: 用户消息
            user_id: 用户 ID

        Returns:
            AgentChatResponse 包含回复内容和工具调用结果
        """
        # 1. 确保会话存在
        await self.session_mgr.create_session(session_id, user_id)

        # 2. 存储用户消息
        await self.session_mgr.append_message(
            session_id,
            {"role": "user", "content": message},
        )

        # 3. 调用 Agent API
        try:
            response: AgentResponse = await self.client.chat(
                session_id=session_id,
                message=message,
                user_id=user_id,
            )
        except AgentClientError as e:
            logger.error("Agent chat failed: %s", e)
            # 存储错误消息
            await self.session_mgr.append_message(
                session_id,
                {
                    "role": "assistant",
                    "content": f"抱歉，智能助手暂时无法响应: {e}",
                },
            )
            return AgentChatResponse(
                session_id=session_id,
                content=f"抱歉，智能助手暂时无法响应。请稍后重试。",
                finish_reason="error",
                tool_calls=[],
            )

        # 4. 构建工具调用结果列表
        tool_calls = self._build_tool_call_results(response.tool_calls)

        # 5. 存储助手消息
        await self.session_mgr.append_message(
            session_id,
            {
                "role": "assistant",
                "content": response.content,
                "tool_calls": [
                    {
                        "tool_name": tc.tool_name,
                        "arguments": tc.arguments,
                        "result": tc.result,
                        "status": tc.status,
                    }
                    for tc in tool_calls
                ] if tool_calls else None,
            },
        )

        # 6. 续期
        await self.session_mgr.renew_session(session_id)

        return AgentChatResponse(
            session_id=session_id,
            content=response.content,
            tool_calls=tool_calls,
            finish_reason=response.finish_reason,
            usage=(
                AgentUsage(
                    prompt_tokens=response.usage.get("prompt_tokens", 0) if response.usage else 0,
                    completion_tokens=response.usage.get("completion_tokens", 0) if response.usage else 0,
                    total_tokens=response.usage.get("total_tokens", 0) if response.usage else 0,
                )
                if response.usage
                else None
            ),
        )

    async def chat_stream(
        self,
        session_id: str,
        message: str,
        user_id: str,
    ) -> AsyncGenerator[str, None]:
        """SSE 流式对话。

        每个 yield 返回一行 SSE 格式字符串: "data: {...}\n\n"
        前端通过 EventSource 或 fetch + ReadableStream 消费。
        """
        # 1. 确保会话存在
        await self.session_mgr.create_session(session_id, user_id)

        # 2. 存储用户消息
        await self.session_mgr.append_message(
            session_id,
            {"role": "user", "content": message},
        )

        # 3. 发送初始事件
        import json
        import time as _time

        yield f"data: {json.dumps({'type': 'start', 'session_id': session_id, 'timestamp': _time.time()}, ensure_ascii=False)}\n\n"

        # 4. 流式调用 Agent
        full_content = ""
        accumulated_tool_calls: List[Dict[str, Any]] = []

        try:
            async for chunk in self.client.chat_stream(
                session_id=session_id,
                message=message,
                user_id=user_id,
            ):
                if chunk.error:
                    yield f"data: {json.dumps({'type': 'error', 'error': chunk.error}, ensure_ascii=False)}\n\n"
                    # 不中断流，继续尝试
                    continue

                if chunk.content:
                    full_content += chunk.content
                    # 逐字发送增量内容
                    yield f"data: {json.dumps({'type': 'content', 'content': chunk.content}, ensure_ascii=False)}\n\n"

                if chunk.tool_calls:
                    for tc in chunk.tool_calls:
                        accumulated_tool_calls.append(tc)
                        yield f"data: {json.dumps({'type': 'tool_call', 'tool_call': tc}, ensure_ascii=False)}\n\n"

                if chunk.finish_reason:
                    finish = chunk.finish_reason
                    usage = chunk.usage

                    # 构建结束事件
                    end_data: Dict[str, Any] = {
                        "type": "done",
                        "session_id": session_id,
                        "finish_reason": finish,
                        "content_length": len(full_content),
                        "tool_calls_count": len(accumulated_tool_calls),
                    }
                    if usage:
                        end_data["usage"] = usage

                    yield f"data: {json.dumps(end_data, ensure_ascii=False)}\n\n"

                    # 存储助手消息
                    await self.session_mgr.append_message(
                        session_id,
                        {
                            "role": "assistant",
                            "content": full_content,
                            "tool_calls": accumulated_tool_calls if accumulated_tool_calls else None,
                        },
                    )

                    # 续期
                    await self.session_mgr.renew_session(session_id)
                    return

        except AgentCircuitOpenError as e:
            logger.error("Agent circuit breaker open during stream: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'error': '服务暂时不可用 (熔断保护)', 'error_code': 'circuit_open'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'finish_reason': 'error'}, ensure_ascii=False)}\n\n"
            return
        except AgentClientError as e:
            logger.error("Agent stream error: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'error': str(e), 'error_code': 'agent_error'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'finish_reason': 'error'}, ensure_ascii=False)}\n\n"
            # 仍然存储部分回复
            if full_content:
                await self.session_mgr.append_message(
                    session_id,
                    {"role": "assistant", "content": full_content + "\n\n[响应中断]"},
                )
            return
        except Exception as e:
            logger.exception("Unexpected stream error: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'error': '内部服务异常', 'error_code': 'internal_error'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'finish_reason': 'error'}, ensure_ascii=False)}\n\n"
            return

        # 某些平台实现可能以 [DONE] 结束但未带 finish_reason。
        await self.session_mgr.append_message(
            session_id,
            {
                "role": "assistant",
                "content": full_content,
                "tool_calls": accumulated_tool_calls if accumulated_tool_calls else None,
            },
        )
        await self.session_mgr.renew_session(session_id)
        done_event = {
            "type": "done",
            "session_id": session_id,
            "finish_reason": "stop",
            "content_length": len(full_content),
            "tool_calls_count": len(accumulated_tool_calls),
        }
        yield f"data: {json.dumps(done_event, ensure_ascii=False)}\n\n"

    # ---- 历史查询 ----

    async def get_history(
        self,
        session_id: str,
        user_id: str,
        limit: int = 50,
    ) -> AgentHistoryResponse:
        """获取会话历史"""
        meta = await self.session_mgr.get_meta(session_id)

        if not meta:
            return AgentHistoryResponse(
                session_id=session_id,
                user_id=user_id,
                messages=[],
            )

        raw_messages = await self.session_mgr.get_history(session_id, limit=limit)

        messages: List[AgentHistoryItem] = []
        for m in raw_messages:
            tc_list = None
            if m.get("tool_calls"):
                tc_list = [
                    ToolCallResult(
                        tool_name=tc.get("tool_name", ""),
                        tool_call_id=tc.get("tool_call_id"),
                        arguments=tc.get("arguments"),
                        result=tc.get("result"),
                        status=tc.get("status", "completed"),
                        error=tc.get("error"),
                    )
                    for tc in m["tool_calls"]
                ]

            messages.append(AgentHistoryItem(
                role=m.get("role", "user"),
                content=m.get("content", ""),
                tool_calls=tc_list,
                timestamp=self._parse_dt(m.get("timestamp")),
            ))

        return AgentHistoryResponse(
            session_id=session_id,
            user_id=meta.get("user_id", user_id),
            messages=messages,
            created_at=self._parse_dt(meta.get("created_at")),
            updated_at=self._parse_dt(meta.get("updated_at")),
            message_count=len(messages),
        )

    # ---- 会话管理 ----

    async def list_user_sessions(self, user_id: str) -> AgentSessionListResponse:
        """列出用户的所有会话"""
        sessions_data = await self.session_mgr.get_user_sessions_detail(user_id)

        sessions: List[AgentSessionInfo] = []
        for s in sessions_data:
            sessions.append(AgentSessionInfo(
                session_id=s.get("session_id", ""),
                user_id=s.get("user_id", user_id),
                message_count=s.get("message_count", 0),
                created_at=self._parse_dt(s.get("created_at")),
                last_active_at=self._parse_dt(s.get("updated_at")),
                ttl_seconds=s.get("ttl_seconds", 0),
            ))

        return AgentSessionListResponse(
            sessions=sessions,
            total=len(sessions),
        )

    async def delete_session(self, session_id: str, user_id: str) -> bool:
        """删除会话"""
        meta = await self.session_mgr.get_meta(session_id)
        if meta and meta.get("user_id") != user_id:
            logger.warning(
                "User %s attempted to delete session %s owned by %s",
                user_id, session_id, meta.get("user_id"),
            )
            return False
        return await self.session_mgr.delete_session(session_id)

    # ---- 辅助方法 ----

    def _build_tool_call_results(
        self,
        raw_tool_calls: List[Dict[str, Any]],
    ) -> List[ToolCallResult]:
        """将 Agent 原始工具调用转为 Schema"""
        results: List[ToolCallResult] = []
        for tc in raw_tool_calls:
            results.append(ToolCallResult(
                tool_name=tc.get("tool_name", "unknown"),
                tool_call_id=tc.get("tool_call_id"),
                arguments=tc.get("arguments"),
                result=tc.get("result"),
                status=tc.get("status", "completed"),
                error=tc.get("error"),
            ))
        return results

    @staticmethod
    def _parse_dt(value: Any) -> Optional[Any]:
        """安全解析日期时间"""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except (ValueError, TypeError):
            return None


# ============================================================================
# 全局单例
# ============================================================================

_agent_service_instance: Optional[AgentService] = None


def get_agent_service() -> AgentService:
    """获取 AgentService 全局单例"""
    global _agent_service_instance
    if _agent_service_instance is None:
        _agent_service_instance = AgentService()
        logger.info("AgentService global singleton created")
    return _agent_service_instance
