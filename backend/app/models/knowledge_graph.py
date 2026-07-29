"""知识图谱边模型 — 前置依赖关系"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.knowledge_point import KnowledgePoint


class KnowledgeGraphEdge(Base):
    __tablename__ = "knowledge_graph"
    __table_args__ = (
        UniqueConstraint(
            "source_kp_id", "target_kp_id", name="uq_knowledge_graph_edge"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="边唯一ID",
    )
    source_kp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="前置知识点ID",
    )
    target_kp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="后置知识点ID",
    )
    relation_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="prerequisite", comment="关系类型"
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
    source_kp: Mapped["KnowledgePoint"] = relationship(
        "KnowledgePoint",
        foreign_keys=[source_kp_id],
        back_populates="outgoing_edges",
    )
    target_kp: Mapped["KnowledgePoint"] = relationship(
        "KnowledgePoint",
        foreign_keys=[target_kp_id],
        back_populates="incoming_edges",
    )

    def __repr__(self) -> str:
        return f"<KnowledgeGraphEdge({self.source_kp_id} → {self.target_kp_id})>"
