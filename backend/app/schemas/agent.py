"""Agent 对话 API 接口契约 — Pydantic v2 模式

字段使用 Python snake_case 定义，通过 CamelModel 自动输出 camelCase JSON。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import Field

from app.schemas.aoo import CamelModel


# ============================================================
# 请求体
# ============================================================


class AgentChatRequest(CamelModel):
    """POST /api/v1/agent/chat — 发送对话消息"""

    session_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="会话 ID，用于多轮对话上下文维护。首次对话由前端生成 UUID",
        examples=["sess_a1b2c3d4e5f6"],
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="用户消息内容",
        examples=["请为我生成学习路径"],
    )
    user_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="学生 / 用户 ID（与系统 User.id 一致）",
        examples=["student_xxx"],
    )
    stream: bool = Field(
        default=True,
        description="是否使用 SSE 流式输出，默认开启",
    )


# ============================================================
# 响应体 — 非流式
# ============================================================


class ToolCallResult(CamelModel):
    """Agent 工具调用的解析结果"""

    tool_name: str = Field(..., description="工具名称", examples=["aoo_path_planning"])
    tool_call_id: Optional[str] = Field(default=None, description="平台工具调用 ID")
    arguments: Optional[Dict[str, Any]] = Field(
        default=None, description="工具调用传入参数"
    )
    result: Optional[Any] = Field(
        default=None, description="工具调用返回结果（已解析）"
    )
    status: str = Field(
        default="completed",
        description="工具调用状态",
        examples=["completed", "failed", "pending"],
    )
    error: Optional[str] = Field(default=None, description="失败时的错误信息")


class AgentUsage(CamelModel):
    """Token 用量"""

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class AgentChatResponse(CamelModel):
    """非流式对话响应"""

    session_id: str = Field(..., description="会话 ID")
    content: str = Field(default="", description="Agent 最终回复文本")
    tool_calls: List[ToolCallResult] = Field(
        default_factory=list, description="工具调用结果列表"
    )
    finish_reason: Optional[str] = Field(
        default=None,
        description="结束原因: stop / tool_calls / length / error",
    )
    usage: Optional[AgentUsage] = Field(default=None, description="Token 用量")
    created_at: Optional[datetime] = Field(default=None, description="响应创建时间")


# ============================================================
# 历史查询
# ============================================================


class AgentHistoryItem(CamelModel):
    """对话历史中的单条消息"""

    role: str = Field(..., description="角色: user / assistant / tool")
    content: str = Field(default="", description="消息内容")
    tool_calls: Optional[List[ToolCallResult]] = Field(
        default=None, description="关联的工具调用"
    )
    timestamp: Optional[datetime] = Field(default=None, description="消息时间")


class AgentHistoryResponse(CamelModel):
    """GET /api/v1/agent/history/{session_id} 响应"""

    session_id: str
    user_id: str
    messages: List[AgentHistoryItem] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    message_count: int = Field(default=0, description="消息总数")


# ============================================================
# 会话管理
# ============================================================


class AgentSessionInfo(CamelModel):
    """会话基本信息"""

    session_id: str
    user_id: str
    message_count: int = 0
    created_at: Optional[datetime] = None
    last_active_at: Optional[datetime] = None
    ttl_seconds: int = Field(default=3600, description="剩余过期秒数")


class AgentSessionListResponse(CamelModel):
    """GET /api/v1/agent/sessions 响应"""

    sessions: List[AgentSessionInfo] = Field(default_factory=list)
    total: int = 0


class AgentDeleteSessionResponse(CamelModel):
    """DELETE /api/v1/agent/sessions/{session_id} 响应"""

    session_id: str
    deleted: bool = True
    message: str = "会话已删除"


# ============================================================
# 反思框（建议 9）— POST /api/v1/chat/reflect
# ============================================================


class ReflectRequest(CamelModel):
    """反思框提交 — 学生针对可复制素材提问，模型判定理解度"""

    session_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="会话 ID，与 /chat/agent 一致，用于维持上下文",
    )
    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="学生向老师提的问题（必填，前端已校验非空）",
    )
    material: str = Field(
        ...,
        min_length=1,
        max_length=8000,
        description="被拦截的可复制素材原文（代码块/提纲），供模型判定依据",
    )


class ReflectResponse(CamelModel):
    """反思判定结果 — 模型判断学生是否真读懂，给对错反馈与一句追问"""

    understood: bool = Field(
        ...,
        description="模型判定学生是否真正读懂素材",
    )
    feedback: str = Field(
        default="",
        description="对错反馈（一句话，指出理解偏差，不直接改正答案）",
    )
    follow_up: str = Field(
        default="",
        description="一句追问，引导学生自己补全理解",
    )


# ============================================================
# 问答画像回流（建议 10）— POST /api/v1/chat/summarize-profile
# ============================================================


class ChatSummarizeRequest(CamelModel):
    """会话结束提炼画像 — 从对话提取结构化掌握度增量"""

    session_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="会话 ID",
    )
    user_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="学生 / 用户 ID",
    )
    authorized: bool = Field(
        default=True,
        description="是否授权本次对话计入学习画像（仅授权才执行提炼与回流）",
    )


class MasteryDelta(CamelModel):
    """单个知识点的掌握度增量"""

    kp_id: str = Field(..., description="知识点 ID")
    delta_mastery: float = Field(
        ...,
        ge=-0.2,
        le=0.2,
        description="掌握度增量（相对测绘基线，范围 -0.2~+0.2）",
    )


class ChatSummarizeResponse(CamelModel):
    """会话画像提炼结果 — 仅基于对话中明确暴露的信号"""

    deltas: List[MasteryDelta] = Field(
        default_factory=list,
        description="知识点掌握度增量列表",
    )
    new_weak_points: List[str] = Field(
        default_factory=list,
        description="新识别的薄弱知识点 ID 列表",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="提炼置信度（0~1）",
    )
    significant: bool = Field(
        default=False,
        description="是否显著（|sum(delta)|>0.3），显著则触发重规划",
    )
    replanned: bool = Field(
        default=False,
        description="是否触发了重规划（生成待采纳新版本）",
    )
    new_version: Optional[int] = Field(
        default=None,
        description="若触发重规划，新路径版本号",
    )


# ============================================================
# 健康检查
# ============================================================


class AgentHealthResponse(CamelModel):
    """GET /api/v1/agent/health — Agent 连通性检查"""

    configured: bool = Field(..., description="是否已配置 API Key 和 Endpoint")
    endpoint: Optional[str] = Field(default=None, description="配置的 API 地址")
    reachable: Optional[bool] = Field(default=None, description="上次连通性检测结果")
    latency_ms: Optional[float] = Field(default=None, description="上次检测延迟 (ms)")
    message: str = Field(default="ok")
