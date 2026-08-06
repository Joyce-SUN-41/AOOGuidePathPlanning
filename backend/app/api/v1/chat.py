"""统一聊天入口（兼容层）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from fastapi import HTTPException, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.agent import (
    AgentChatRequest,
    AgentChatResponse,
    ChatSummarizeRequest,
    ChatSummarizeResponse,
    ReflectRequest,
    ReflectResponse,
)
from app.schemas.common import ResponseBase
from app.services.agent import get_agent_service
from app.services.chat import profile_reflector as pr

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post(
    "/agent",
    response_model=ResponseBase[AgentChatResponse],
    summary="通过统一聊天入口调用 Agent",
)
async def chat_agent(
    request: AgentChatRequest,
    current_user: User = Depends(get_current_user),
):
    service = get_agent_service()
    if request.stream:
        stream = service.chat_stream(
            session_id=request.session_id,
            message=request.message,
            user_id=str(current_user.id),
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
        user_id=str(current_user.id),
    )
    return ResponseBase(data=result)


# ============================================================
# 反思框（建议 9）— 判定学生是否真读懂素材
# ============================================================


@router.post(
    "/reflect",
    response_model=ResponseBase[ReflectResponse],
    summary="反思框：判定学生对可复制素材的理解度",
)
async def chat_reflect(
    request: ReflectRequest,
    current_user: User = Depends(get_current_user),
):
    understood, feedback, follow_up = await pr.reflect(
        session_id=request.session_id,
        question=request.question,
        material=request.material,
    )
    return ResponseBase(data=ReflectResponse(
        understood=understood,
        feedback=feedback,
        follow_up=follow_up,
    ))


# ============================================================
# 问答画像回流（建议 10）— 会话结束提炼画像并可能触发重规划
# ============================================================


@router.post(
    "/summarize-profile",
    response_model=ResponseBase[ChatSummarizeResponse],
    summary="会话提炼画像：从对话提取掌握度增量并驱动重规划",
)
async def chat_summarize_profile(
    request: ChatSummarizeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if request.authorized and request.user_id != str(current_user.id):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="授权用户与当前登录用户不一致",
        )
    result = await pr.summarize_profile(
        db=db,
        session_id=request.session_id,
        user_id=str(current_user.id),
        authorized=request.authorized,
    )
    return ResponseBase(data=ChatSummarizeResponse(**result))
