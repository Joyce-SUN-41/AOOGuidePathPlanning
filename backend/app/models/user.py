"""用户模型"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.student_knowledge import StudentKnowledge
    from app.models.learning_path import LearningPath
    from app.models.cognitive_load_record import CognitiveLoadRecord
    from app.models.chat_history import ChatHistory
    from app.models.aoo_optimization_log import AOOOptimizationLog
    from app.models.diagnosis import DiagnosisRecord


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="用户唯一ID",
    )
    username: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True, comment="用户名"
    )
    nickname: Mapped[str] = mapped_column(
        String(50), nullable=True, index=False, comment="昵称（显示名称）"
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=True, index=True, comment="邮箱"
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="加密密码"
    )
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="student",
        comment="角色: student | teacher",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="是否激活"
    )
    is_superuser: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否超级管理员"
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

    # ---- 关系 ----
    student_knowledge: Mapped[List["StudentKnowledge"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )
    learning_paths: Mapped[List["LearningPath"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )
    cognitive_load_records: Mapped[List["CognitiveLoadRecord"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )
    chat_histories: Mapped[List["ChatHistory"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )
    aoo_optimization_logs: Mapped[List["AOOOptimizationLog"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )
    diagnosis_records: Mapped[List["DiagnosisRecord"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username}, role={self.role})>"
