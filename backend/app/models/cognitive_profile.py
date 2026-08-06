"""学生认知画像模型

P1 新增。核心约束（来自 2026-08-02 决策）:
  - StudentKnowledge 不可被问答信号污染，问答增量单独存于 mastery_deltas (JSONB)
  - 融合仅在内存中进行（见 services/cehui/adapter.py），本表只沉淀问答增量
  - 无测绘基线时，mastery_deltas 作为微弱先验参与融合，不回写 StudentKnowledge

P5 新增 ChatMasteryProfile:
  - 仅沉淀「导学终端」通过对话梳理出的该生知识点掌握特点（绝对掌握度视图）
  - 与 StudentKnowledge（客观答题）和 StudentCognitiveProfile（相对增量）三者分离
  - 仅用于「对话画像」展示与「测绘 + 对话」重规划融合，绝不回写客观数据
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class StudentCognitiveProfile(Base):
    """学生认知画像：沉淀对话即测绘 (CSP) 产生的问答增量

    与 StudentKnowledge 严格分离：StudentKnowledge 只存客观答题记录的掌握度，
    本表只存对话问答产生的 mastery_deltas (相对增量)，二者在内存里融合，
    绝不互相覆盖落库。
    """

    __tablename__ = "student_cognitive_profiles"
    __table_args__ = (
        UniqueConstraint("student_id", name="uq_student_cognitive_profile"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="画像ID",
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="学生用户ID",
    )
    # 问答增量: { kp_id(str): { "delta": float, "confidence": float, "n": int, "last_at": str } }
    # 仅记录对话问答对掌握度的修正，不存绝对掌握度，避免与 StudentKnowledge 语义冲突
    mastery_deltas: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, default=dict, comment="问答增量 (JSONB)，按 kp_id 索引"
    )
    # 累计问答信号条数（含被丢弃/未对齐，用于可观测性，不进融合）
    chat_signal_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="累计接收的问答信号条数"
    )
    last_chat_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), comment="最近一次问答信号时间"
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
        "User", back_populates="cognitive_profiles"
    )

    def __repr__(self) -> str:
        return (
            f"<StudentCognitiveProfile(student={self.student_id}, "
            f"deltas={len(self.mastery_deltas)})>"
        )


class CognitiveProfileEvent(Base):
    """认知画像事件：可观测性落库，解释每一次画像/路径变化的原因

    reasoning 字段是后续向用户解释「为什么路径变了」的唯一依据，必须完整落库。
    """

    __tablename__ = "cognitive_profile_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="事件ID",
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="学生用户ID",
    )
    # 事件类型: chat_signal | fusion | aoo_trigger | path_regenerate | baseline_fallback
    event_type: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True, comment="事件类型"
    )
    # 关联的知识点（若有）
    kp_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="关联知识点ID",
    )
    # 事件详情（原始信号、融合前后值等）
    payload: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, default=dict, comment="事件详情 (JSONB)"
    )
    # 关键可观测字段：解释「为什么」
    reasoning: Mapped[str] = mapped_column(
        Text, default="", comment="决策推理说明，向用户解释变化原因的唯一依据"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        comment="创建时间",
    )

    # ---- 关系 ----
    student: Mapped["User"] = relationship(
        "User", back_populates="cognitive_profile_events"
    )

    def __repr__(self) -> str:
        return (
            f"<CognitiveProfileEvent(type={self.event_type}, "
            f"student={self.student_id}, kp={self.kp_id})>"
        )


class ChatMasteryProfile(Base):
    """导学终端对话画像 — 仅沉淀"通过对话梳理出的该生知识点掌握特点"

    设计原则（数据真实性底线）:
      - 与 StudentKnowledge（客观答题掌握度）严格分离，绝不互相覆盖
      - 与 StudentCognitiveProfile（相对增量）分离，本表存「绝对掌握度视图」
      - 仅来源于导学终端中 LLM 梳理出的 mastery_estimates
      - 用途: ① 在导学终端页「对话画像」抽屉中可查看 ② 作为「测绘 + 对话」重规划融合的会话内主观来源

    结构:
      mastery: { kp_id(str): {
          "level": float,           # 对话梳理出的掌握度估计 [0,1]
          "confidence": float,      # 该估计的置信度 [0,1]
          "n": int,                 # 被对话提及/修正的次数（置信度累积依据）
          "last_at": str,           # 最近一次更新时间 (ISO)
          "source": str,            # 最近一次来源（如 "chat"）
      } }
    """

    __tablename__ = "chat_mastery_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="对话画像ID",
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="学生用户ID",
    )
    # 对话梳理出的掌握特点（绝对视图，按 kp_id 索引）
    mastery: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, default=dict, comment="对话掌握特点 (JSONB) {kp_id: {level, confidence, n, last_at, source}}"
    )
    # 累计从对话接收并成功对齐的信号条数（可观测性）
    chat_signal_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="累计对话信号条数"
    )
    last_chat_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), comment="最近一次对话信号时间"
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
        "User", back_populates="chat_mastery_profile"
    )

    def __repr__(self) -> str:
        return (
            f"<ChatMasteryProfile(student={self.student_id}, "
            f"kps={len(self.mastery)})>"
        )
