"""学生认知画像与事件表

Revision ID: 007_cognitive_profile
Revises: 006_add_avatar_and_phone
Create Date: 2026-08-02

P1 新增（2026-08-02 决策）:
  1. student_cognitive_profiles — 对话即诊断(CSP)问答增量沉淀
     - mastery_deltas (JSONB) 仅存问答相对增量，不污染 StudentKnowledge
  2. cognitive_profile_events — 可观测性落库，reasoning 字段是
     解释「为什么路径变了」的唯一依据
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision: str = "007_cognitive_profile"
down_revision: Union[str, None] = "006_add_avatar_and_phone"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "student_cognitive_profiles",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            comment="画像ID",
        ),
        sa.Column(
            "student_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            comment="学生用户ID",
        ),
        sa.Column(
            "mastery_deltas",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="问答增量 (JSONB)，按 kp_id 索引",
        ),
        sa.Column(
            "chat_signal_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="累计接收的问答信号条数",
        ),
        sa.Column(
            "last_chat_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最近一次问答信号时间",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            comment="更新时间",
        ),
        sa.UniqueConstraint("student_id", name="uq_student_cognitive_profile"),
    )
    op.create_index(
        "ix_student_cognitive_profiles_student_id",
        "student_cognitive_profiles",
        ["student_id"],
    )

    op.create_table(
        "cognitive_profile_events",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            comment="事件ID",
        ),
        sa.Column(
            "student_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            comment="学生用户ID",
        ),
        sa.Column(
            "event_type",
            sa.String(30),
            nullable=False,
            comment="事件类型",
        ),
        sa.Column(
            "kp_id",
            UUID(as_uuid=True),
            nullable=True,
            comment="关联知识点ID",
        ),
        sa.Column(
            "payload",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="事件详情 (JSONB)",
        ),
        sa.Column(
            "reasoning",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
            comment="决策推理说明",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            comment="创建时间",
        ),
    )
    op.create_index(
        "ix_cognitive_profile_events_student_id",
        "cognitive_profile_events",
        ["student_id"],
    )
    op.create_index(
        "ix_cognitive_profile_events_event_type",
        "cognitive_profile_events",
        ["event_type"],
    )
    op.create_index(
        "ix_cognitive_profile_events_kp_id",
        "cognitive_profile_events",
        ["kp_id"],
    )
    op.create_index(
        "ix_cognitive_profile_events_created_at",
        "cognitive_profile_events",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_table("cognitive_profile_events")
    op.drop_table("student_cognitive_profiles")
