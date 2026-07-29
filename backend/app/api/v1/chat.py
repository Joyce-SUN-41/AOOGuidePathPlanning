"""统一聊天入口（兼容层）。"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.schemas.agent import AgentChatRequest, AgentChatResponse
from app.schemas.common import ResponseBase
from app.services.agent import get_agent_service

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post(
    "/agent",
    response_model=ResponseBase[AgentChatResponse],
    summary="通过统一聊天入口调用 Agent",
)
async def chat_agent(request: AgentChatRequest):
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

    result = await service.chat(
        session_id=request.session_id,
        message=request.message,
        user_id=request.user_id,
    )
    return ResponseBase(data=result)
