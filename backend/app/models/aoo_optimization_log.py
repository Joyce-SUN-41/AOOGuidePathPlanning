"""AOO 寻优日志模型"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class AOOOptimizationLog(Base):
    __tablename__ = "aoo_optimization_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="日志ID",
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="学生用户ID",
    )
    iteration: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="迭代轮次"
    )
    best_fitness: Mapped[Optional[float]] = mapped_column(
        Float, comment="最佳适应度"
    )
    avg_fitness: Mapped[Optional[float]] = mapped_column(
        Float, comment="平均适应度"
    )
    diversity: Mapped[Optional[float]] = mapped_column(
        Float, comment="种群多样性"
    )
    convergence_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, default=dict, comment="收敛详细数据 (JSONB)"
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
        "User", back_populates="aoo_optimization_logs"
    )

    def __repr__(self) -> str:
        return (
            f"<AOOOptimizationLog(id={self.id}, "
            f"student={self.student_id}, iter={self.iteration})>"
        )
