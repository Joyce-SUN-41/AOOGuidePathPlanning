"""题库题目模型"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.knowledge_point import KnowledgePoint


class Question(Base):
    """测绘题库题目"""

    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="题目唯一ID",
    )
    code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True, comment="题目编号, 如 q_ai_001"
    )
    kp_ids: Mapped[List] = mapped_column(
        JSONB, nullable=False, default=list, comment="关联知识点ID列表"
    )
    subject: Mapped[str] = mapped_column(
        String(100), nullable=False, default="人工智能导论", index=True, comment="学科"
    )
    difficulty: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="难度: 1-5"
    )
    type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="single", comment="题型: single | multiple"
    )
    title: Mapped[str] = mapped_column(
        Text, nullable=False, comment="题目文本"
    )
    options: Mapped[List] = mapped_column(
        JSONB, nullable=False, default=list, comment="选项列表 [{id, text, weight}]"
    )
    correct_option_id: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="正确选项ID"
    )
    expected_time_sec: Mapped[float] = mapped_column(
        Integer, nullable=False, default=20, comment="预期答题时间(秒)"
    )
    explanation: Mapped[Optional[str]] = mapped_column(
        Text, comment="答案解析"
    )
    is_active: Mapped[bool] = mapped_column(
        default=True, comment="是否启用"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )

    def __repr__(self) -> str:
        return f"<Question(id={self.id}, code={self.code}, difficulty={self.difficulty})>"
