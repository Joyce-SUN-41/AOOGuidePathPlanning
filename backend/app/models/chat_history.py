"""问答历史模型"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="问答ID",
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="学生用户ID",
    )
    question: Mapped[str] = mapped_column(
        Text, nullable=False, comment="用户问题"
    )
    answer: Mapped[str] = mapped_column(
        Text, nullable=False, comment="系统回答"
    )
    sources: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, default=list, comment="引用溯源 [{kp_id, content, score}]"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )

    # ---- 关系 ----
    student: Mapped["User"] = relationship(
        "User", back_populates="chat_histories"
    )

    def __repr__(self) -> str:
        return f"<ChatHistory(id={self.id}, student={self.student_id})>"
