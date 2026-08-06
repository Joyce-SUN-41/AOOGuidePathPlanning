"""学习路径模型"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
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
    # ---- P2 重规划版本管理 ----
    # parent_path_id: 本次重规划基于的旧路径（新版本指向旧版本，形成链路）
    # version: 同一学生的路径版本号，从 1 递增
    # is_active: 当前是否生效（待采纳的新版本为 False，采纳后置 True，旧版本置 False）
    parent_path_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_paths.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="父路径ID（重规划来源版本）",
    )
    version: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False, comment="路径版本号"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True, comment="是否为当前生效路径"
    )
    # 规划类型语义标签: baseline=起点规划(测绘首轮); update_vN=问答回流触发的动态更新第N版
    # 旧路径该字段为空, 前端按 baseline 向后兼容显示
    plan_type: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, comment="规划类型: baseline=起点规划, update_vN=动态更新第N版"
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
