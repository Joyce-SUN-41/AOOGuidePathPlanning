"""讯飞星辰 Agent 对话 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user
from app.models.user import User
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
async def agent_chat(
    request: AgentChatRequest,
    current_user: User = Depends(get_current_user),
):
    service = get_agent_service()
    user_id = request.user_id or str(current_user.id)

    if request.stream:
        stream = service.chat_stream(
            session_id=request.session_id,
            message=request.message,
            user_id=user_id,
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
        user_id=user_id,
    )
    return ResponseBase(data=response)


@router.get(
    "/history/{session_id}",
    response_model=ResponseBase[AgentHistoryResponse],
    summary="查询会话历史",
)
async def get_agent_history(
    session_id: str,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    service = get_agent_service()
    history = await service.get_history(
        session_id=session_id, user_id=str(current_user.id), limit=limit
    )
    return ResponseBase(data=history)


@router.get(
    "/sessions",
    response_model=ResponseBase[AgentSessionListResponse],
    summary="查询用户会话列表",
)
async def list_agent_sessions(
    current_user: User = Depends(get_current_user),
):
    service = get_agent_service()
    sessions = await service.list_user_sessions(user_id=str(current_user.id))
    return ResponseBase(data=sessions)


@router.delete(
    "/sessions/{session_id}",
    response_model=ResponseBase[AgentDeleteSessionResponse],
    summary="删除会话",
)
async def delete_agent_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    service = get_agent_service()
    deleted = await service.delete_session(
        session_id=session_id, user_id=str(current_user.id)
    )
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
async def agent_health(
    current_user: User = Depends(get_current_user),
):
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
