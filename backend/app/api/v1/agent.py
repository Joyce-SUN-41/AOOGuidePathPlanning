"""讯飞星辰 Agent 对话 API。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.schemas.agent import (
    AgentChatRequest,
    AgentChatResponse,
    AgentDeleteSessionResponse,
    AgentHealthResponse,
    AgentHistoryResponse,
    AgentSessionListResponse,
)
from app.schemas.common import ResponseBase
from app.services.agent import get_agent_service

router = APIRouter(prefix="/agent", tags=["Agent"])


@router.post(
    "/chat",
    response_model=ResponseBase[AgentChatResponse],
    summary="调用讯飞星辰 Agent 对话",
    description="支持 JSON 一次性返回或 SSE 流式返回。",
)
async def agent_chat(request: AgentChatRequest):
    service = get_agent_service()

    if request.stream:
        stream = service.chat_stream(
            session_id=request.session_id,
            message=request.message,
            user_id=request.user_id,
        )
        return StreamingResponse(
            stream,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    response = await service.chat(
        session_id=request.session_id,
        message=request.message,
        user_id=request.user_id,
    )
    return ResponseBase(data=response)


@router.get(
    "/history/{session_id}",
    response_model=ResponseBase[AgentHistoryResponse],
    summary="查询会话历史",
)
async def get_agent_history(
    session_id: str,
    user_id: str = Query(..., description="学生/用户 ID"),
    limit: int = Query(50, ge=1, le=200),
):
    service = get_agent_service()
    history = await service.get_history(session_id=session_id, user_id=user_id, limit=limit)
    return ResponseBase(data=history)


@router.get(
    "/sessions",
    response_model=ResponseBase[AgentSessionListResponse],
    summary="查询用户会话列表",
)
async def list_agent_sessions(
    user_id: str = Query(..., description="学生/用户 ID"),
):
    service = get_agent_service()
    sessions = await service.list_user_sessions(user_id=user_id)
    return ResponseBase(data=sessions)


@router.delete(
    "/sessions/{session_id}",
    response_model=ResponseBase[AgentDeleteSessionResponse],
    summary="删除会话",
)
async def delete_agent_session(
    session_id: str,
    user_id: str = Query(..., description="学生/用户 ID"),
):
    service = get_agent_service()
    deleted = await service.delete_session(session_id=session_id, user_id=user_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权删除该会话",
        )
    return ResponseBase(
        data=AgentDeleteSessionResponse(session_id=session_id, deleted=True)
    )


@router.get(
    "/health",
    response_model=ResponseBase[AgentHealthResponse],
    summary="Agent 配置检查",
)
async def agent_health():
    service = get_agent_service()
    client = service.client
    data = AgentHealthResponse(
        configured=client.is_configured,
        endpoint=client.chat_endpoint if client.base_url else None,
        reachable=None,
        latency_ms=None,
        message="ok" if client.is_configured else "missing api config",
    )
    return ResponseBase(data=data)
