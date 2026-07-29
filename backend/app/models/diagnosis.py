"""诊断记录模型 — 存储每次认知诊断测验的完整结果"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class DiagnosisRecord(Base):
    """诊断记录表 — 每次诊断测验生成一条记录"""

    __tablename__ = "diagnosis_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="诊断记录唯一 ID",
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="学生用户 ID",
    )
    subject: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="mathematics",
        index=True,
        comment="学科",
    )
    grade: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="",
        comment="年级",
    )
    answers: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="完整答题记录 [{question_id, selected_option, time_spent, is_correct, kp_id}, ...]",
    )
    mastery_levels: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="各知识点掌握度 {kp_id: {mastery, level, confidence, name}}",
    )
    cognitive_load: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="认知负荷画像 {memory_load, attention_load, processing_load, overall}",
    )
    cognitive_load_index: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="综合认知负荷指数 0-1",
    )
    weak_points: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="薄弱点列表 [{kp_id, knowledge_point, reason, severity, suggested_remediation}]",
    )
    radar_data: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="雷达图数据 {dimension: value}",
    )
    overall_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="综合评分 0-100",
    )
    learning_style: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="未评估",
        comment="推断的学习风格标签",
    )
    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        comment="AI 诊断摘要",
    )
    total_questions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="总题数",
    )
    correct_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="答对题数",
    )
    average_time_spent: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="平均答题时间(秒)",
    )
    expected_average_time: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=15.0,
        comment="预期平均答题时间(秒)",
    )
    consecutive_errors: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="最大连续错误数",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        comment="创建时间",
    )

    # ---- 关系 ----
    student: Mapped["User"] = relationship(
        "User", back_populates="diagnosis_records"
    )

    def __repr__(self) -> str:
        return (
            f"<DiagnosisRecord(id={self.id}, student={self.student_id}, "
            f"score={self.overall_score:.1f})>"
        )
