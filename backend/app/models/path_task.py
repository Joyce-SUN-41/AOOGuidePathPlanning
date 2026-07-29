"""路径任务模型"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.learning_path import LearningPath
    from app.models.knowledge_point import KnowledgePoint


class PathTask(Base):
    __tablename__ = "path_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="任务ID",
    )
    path_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_paths.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属路径ID",
    )
    kp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="对应知识点ID",
    )
    day_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="第几天 (从1开始)"
    )
    order_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="当天任务顺序"
    )
    task_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="reading",
        comment="任务类型: video | quiz | reading | project",
    )
    estimated_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=15, comment="预估分钟数"
    )
    completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True, comment="是否完成"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )

    # ---- 关系 ----
    learning_path: Mapped["LearningPath"] = relationship(
        "LearningPath", back_populates="tasks"
    )
    knowledge_point: Mapped["KnowledgePoint"] = relationship(
        "KnowledgePoint", back_populates="path_tasks"
    )

    def __repr__(self) -> str:
        return (
            f"<PathTask(id={self.id}, day={self.day_index}, "
            f"order={self.order_index}, type={self.task_type})>"
        )
