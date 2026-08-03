"""埋点采集 API — 前端行为事件上报

端点:
- POST /api/v1/analytics/track  批量上报埋点事件

设计约束:
1. **允许匿名** —— navigator.sendBeacon 无法携带 Authorization 头，
   因此使用可选认证；有 Token 时补全 user_id，无 Token 时记为匿名。
2. **永不失败** —— 埋点不能影响主业务，任何异常都吞掉并返回 200，
   避免前端 sendBeacon/fetch 产生噪声错误。
3. **零迁移** —— 事件写入结构化日志（JSON Lines），不新增数据库表，
   后续如需入库可由离线任务消费日志文件。
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.deps import get_current_user_optional
from app.models.user import User
from app.schemas.common import ResponseBase

router = APIRouter(prefix="/analytics", tags=["Analytics"])

logger = logging.getLogger(__name__)

# 埋点专用 logger —— 与业务日志分流，便于单独采集/轮转
event_logger = logging.getLogger("app.analytics.events")

# 单批次最大事件数，防止恶意超大 payload
MAX_EVENTS_PER_BATCH = 50
# 单个事件 properties 序列化后的最大长度
MAX_PROPS_LENGTH = 4000


class TrackEvent(BaseModel):
    """单条埋点事件"""

    event: str = Field(..., max_length=100, description="事件名，如 page_view / click")
    timestamp: Optional[int] = Field(
        default=None, description="客户端毫秒时间戳"
    )
    page: Optional[str] = Field(default=None, max_length=500, description="页面路径")
    properties: Dict[str, Any] = Field(
        default_factory=dict, description="自定义属性"
    )


class TrackRequest(BaseModel):
    """埋点批量上报请求"""

    events: List[TrackEvent] = Field(default_factory=list, description="事件列表")
    session_id: Optional[str] = Field(
        default=None, max_length=100, description="前端会话 ID"
    )


class TrackResult(BaseModel):
    """埋点上报结果"""

    received: int = Field(default=0, description="已接收的事件数")


def _safe_props(props: Dict[str, Any]) -> Dict[str, Any]:
    """裁剪过大的属性，避免日志被撑爆"""
    try:
        serialized = json.dumps(props, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return {"_invalid": True}
    if len(serialized) > MAX_PROPS_LENGTH:
        return {"_truncated": True, "_size": len(serialized)}
    return props


@router.post("/track", response_model=ResponseBase[TrackResult])
async def track_events(
    payload: TrackRequest,
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """接收前端埋点事件（允许匿名）

    始终返回 200 —— 埋点失败不应影响用户主流程。
    """
    received = 0
    try:
        events = payload.events[:MAX_EVENTS_PER_BATCH]
        user_id = str(current_user.id) if current_user else None
        server_ts = datetime.now(timezone.utc).isoformat()
        user_agent = request.headers.get("user-agent", "")[:300]

        for ev in events:
            record = {
                "ts": server_ts,
                "client_ts": ev.timestamp,
                "event": ev.event,
                "page": ev.page,
                "user_id": user_id,
                "session_id": payload.session_id,
                "ua": user_agent,
                "props": _safe_props(ev.properties),
            }
            event_logger.info(json.dumps(record, ensure_ascii=False, default=str))
            received += 1

    except Exception:  # noqa: BLE001 — 埋点绝不向上抛错
        logger.exception("[/analytics/track] 埋点处理异常（已忽略）")

    return ResponseBase[TrackResult](data=TrackResult(received=received))
