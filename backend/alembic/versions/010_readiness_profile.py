"""诊断记录增加学习准备度字段

Revision ID: 010_readiness_profile
Revises: 009_chat_mastery_profile
Create Date: 2026-08-04

建议 3（诊断至少二维，争取三维）:
  diagnosis_records 表新增 readiness_profile (JSONB)，存储第三维「学习准备度」
  自陈量表结果 {motivation, metacognition, self_efficacy} 0-1。
  默认空 dict，向后兼容旧记录（旧记录视为未填写，规划器走二维模式）。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "010_readiness_profile"
down_revision: Union[str, Sequence[str], None] = "009_chat_mastery_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "diagnosis_records",
        sa.Column(
            "readiness_profile",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="学习准备度画像 {motivation, metacognition, self_efficacy} 0-1",
        ),
    )


def downgrade() -> None:
    op.drop_column("diagnosis_records", "readiness_profile")
