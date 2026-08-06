"""学习路径增加规划类型标签 plan_type

Revision ID: 012_plan_type
Revises: 011_learning_style_profile
Create Date: 2026-08-04

建议 11（学情测绘后的规划命名为"起点规划"）:
  learning_paths 表新增 plan_type (VARCHAR(32), 可空)，
  语义标签: baseline=起点规划(诊断首轮); update_vN=问答回流触发的动态更新第N版。
  可空以向后兼容旧路径（旧路径前端按 baseline 显示）。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "012_plan_type"
down_revision: Union[str, Sequence[str], None] = "011_learning_style_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "learning_paths",
        sa.Column(
            "plan_type",
            sa.String(length=32),
            nullable=True,
            comment="规划类型: baseline=起点规划, update_vN=动态更新第N版",
        ),
    )


def downgrade() -> None:
    op.drop_column("learning_paths", "plan_type")
