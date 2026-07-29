"""认知负荷记录模型"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class CognitiveLoadRecord(Base):
    __tablename__ = "cognitive_load_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="记录ID",
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="学生用户ID",
    )
    load_score: Mapped[float] = mapped_column(
        Float, nullable=False, comment="负荷评分: 0.0-1.0"
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        comment="记录时间",
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
    context: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="study",
        comment="上下文: diagnostic | study",
    )

    # ---- 关系 ----
    student: Mapped["User"] = relationship(
        "User", back_populates="cognitive_load_records"
    )

    def __repr__(self) -> str:
        return (
            f"<CognitiveLoadRecord(id={self.id}, student={self.student_id}, "
            f"score={self.load_score:.2f})>"
        )
