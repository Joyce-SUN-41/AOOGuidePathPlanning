"""知识点模型"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.knowledge_graph import KnowledgeGraphEdge
    from app.models.student_knowledge import StudentKnowledge
    from app.models.path_task import PathTask


class KnowledgePoint(Base):
    __tablename__ = "knowledge_points"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="知识点唯一ID",
    )
    name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="知识点名称"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, comment="知识点描述"
    )
    subject: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="学科"
    )
    difficulty_level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="难度: 1-5"
    )
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_points.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="父知识点ID (层级结构)",
    )
    layer: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="层级: 基础层/核心层/进阶层"
    )
    tags: Mapped[List[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]", comment="标签列表"
    )
    metadata_: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "metadata", JSONB, nullable=True, default=dict, comment="扩展元数据"
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

    # ---- 自关联 ----
    parent: Mapped[Optional["KnowledgePoint"]] = relationship(
        "KnowledgePoint",
        remote_side="KnowledgePoint.id",
        back_populates="children",
        foreign_keys=[parent_id],
    )
    children: Mapped[List["KnowledgePoint"]] = relationship(
        "KnowledgePoint",
        back_populates="parent",
        foreign_keys=[parent_id],
    )

    # ---- 关系 ----
    outgoing_edges: Mapped[List["KnowledgeGraphEdge"]] = relationship(
        "KnowledgeGraphEdge",
        foreign_keys="KnowledgeGraphEdge.source_kp_id",
        back_populates="source_kp",
        cascade="all, delete-orphan",
    )
    incoming_edges: Mapped[List["KnowledgeGraphEdge"]] = relationship(
        "KnowledgeGraphEdge",
        foreign_keys="KnowledgeGraphEdge.target_kp_id",
        back_populates="target_kp",
        cascade="all, delete-orphan",
    )
    student_knowledge: Mapped[List["StudentKnowledge"]] = relationship(
        back_populates="knowledge_point", cascade="all, delete-orphan"
    )
    path_tasks: Mapped[List["PathTask"]] = relationship(
        back_populates="knowledge_point", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<KnowledgePoint(id={self.id}, name={self.name})>"
