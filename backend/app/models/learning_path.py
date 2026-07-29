"""学习路径模型"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.path_task import PathTask


class LearningPath(Base):
    __tablename__ = "learning_paths"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="路径ID",
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="学生用户ID",
    )
    path_data: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, comment="路径结构数据 (JSONB)"
    )
    total_duration: Mapped[Optional[int]] = mapped_column(
        Integer, comment="预计总时长 (分钟)"
    )
    estimated_completion_days: Mapped[Optional[int]] = mapped_column(
        Integer, comment="预计完成天数"
    )
    fitness_score: Mapped[Optional[float]] = mapped_column(
        Float, index=True, comment="AOO 适应度得分"
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
        "User", back_populates="learning_paths"
    )
    tasks: Mapped[List["PathTask"]] = relationship(
        "PathTask", back_populates="learning_path", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<LearningPath(id={self.id}, student={self.student_id})>"
