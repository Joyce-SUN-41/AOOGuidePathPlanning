"""智能问答对话画像表

Revision ID: 009_chat_mastery_profile
Revises: 008_learning_path_version
Create Date: 2026-08-02

P5 新增（2026-08-02 决策）:
  chat_mastery_profiles 表 — 仅沉淀「智能问答」通过对话梳理出的该生知识点掌握特点。
  与 student_knowledge（客观答题）和 student_cognitive_profiles（相对增量）三者分离，
  只用于「对话画像」展示与「诊断 + 对话」重规划融合，绝不回写客观数据。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision: str = "009_chat_mastery_profile"
down_revision: Union[str, None] = "008_learning_path_version"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_mastery_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "student_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mastery", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "chat_signal_count",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_chat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_chat_mastery_profiles_student_id",
        "chat_mastery_profiles",
        ["student_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_chat_mastery_profiles_student_id", table_name="chat_mastery_profiles")
    op.drop_table("chat_mastery_profiles")
