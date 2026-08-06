"""诊断记录增加学习风格画像字段

Revision ID: 011_learning_style_profile
Revises: 010_readiness_profile
Create Date: 2026-08-04

建议 4（学习风格作为独立自变量纳入 AOO 规划）:
  diagnosis_records 表新增 learning_style_profile (JSONB, 可空)，
  存储学习风格推断结果 {label, scores:{ambitious,sequential,steady,exploratory}}。
  与 learning_style (str 标签) 并存：str 用于向后兼容与快速展示，
  profile 提供分维度得分供前端细化展示。
  可空以向后兼容旧记录（旧记录 learning_style='未评估'，规划器关闭风格偏置）。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "011_learning_style_profile"
down_revision: Union[str, Sequence[str], None] = "010_readiness_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "diagnosis_records",
        sa.Column(
            "learning_style_profile",
            JSONB,
            nullable=True,
            comment="学习风格画像 {label, scores:{ambitious,sequential,steady,exploratory}}",
        ),
    )


def downgrade() -> None:
    op.drop_column("diagnosis_records", "learning_style_profile")
