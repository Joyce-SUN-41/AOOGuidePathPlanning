"""学生知识点掌握度模型"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Float, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.knowledge_point import KnowledgePoint


class StudentKnowledge(Base):
    __tablename__ = "student_knowledge"
    __table_args__ = (
        UniqueConstraint("student_id", "kp_id", name="uq_student_knowledge"),
    )

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
    kp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="知识点ID",
    )
    mastery_level: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="掌握度: 0.0-1.0"
    )
    last_assessed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), comment="最近评估时间"
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
    student: Mapped["User"] = relationship(
        "User", back_populates="student_knowledge"
    )
    knowledge_point: Mapped["KnowledgePoint"] = relationship(
        "KnowledgePoint", back_populates="student_knowledge"
    )

    def __repr__(self) -> str:
        return (
            f"<StudentKnowledge(student={self.student_id}, "
            f"kp={self.kp_id}, mastery={self.mastery_level:.2f})>"
        )
