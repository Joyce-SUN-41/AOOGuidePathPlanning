"""添加 questions 题库表 + 扩展 knowledge_points 字段

Revision ID: 003_question_bank
Revises: 002_diagnosis
Create Date: 2026-07-27

为题库与知识点管理功能新增:
  - questions 表: 持久化诊断题库
  - knowledge_points 新增 layer / tags 列 (JSONB)
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision: str = "003_question_bank"
down_revision: Union[str, None] = "002_diagnosis"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. 创建 questions 表 ──
    op.create_table(
        "questions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            comment="题目唯一ID",
        ),
        sa.Column(
            "code",
            sa.String(50),
            unique=True,
            nullable=False,
            index=True,
            comment="题目编号, 如 q_ai_001",
        ),
        sa.Column(
            "kp_ids",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
            comment="关联知识点ID列表",
        ),
        sa.Column(
            "subject",
            sa.String(100),
            nullable=False,
            server_default="人工智能导论",
            index=True,
            comment="学科",
        ),
        sa.Column("difficulty", sa.Integer, nullable=False, comment="难度: 1-5"),
        sa.Column(
            "type",
            sa.String(20),
            nullable=False,
            server_default="single",
            comment="题型: single | multiple",
        ),
        sa.Column("title", sa.Text, nullable=False, comment="题目文本"),
        sa.Column(
            "options",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
            comment="选项列表 [{id, text, weight}]",
        ),
        sa.Column(
            "correct_option_id",
            sa.String(10),
            nullable=False,
            comment="正确选项ID",
        ),
        sa.Column(
            "expected_time_sec",
            sa.Integer,
            nullable=False,
            server_default="20",
            comment="预期答题时间(秒)",
        ),
        sa.Column("explanation", sa.Text, comment="答案解析"),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
            comment="是否启用",
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
            comment="更新时间",
        ),
    )

    # ── 2. knowledge_points 扩展字段 ──
    op.add_column(
        "knowledge_points",
        sa.Column("layer", sa.String(50), comment="层级: 基础层/核心层/进阶层"),
    )
    op.add_column(
        "knowledge_points",
        sa.Column(
            "tags",
            JSONB,
            server_default=sa.text("'[]'::jsonb"),
            comment="标签列表",
        ),
    )


def downgrade() -> None:
    op.drop_table("questions")
    op.drop_column("knowledge_points", "tags")
    op.drop_column("knowledge_points", "layer")
