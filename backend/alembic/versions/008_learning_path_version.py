"""学习路径版本管理字段

Revision ID: 008_learning_path_version
Revises: 007_cognitive_profile
Create Date: 2026-08-02

P2 新增（2026-08-02 决策）:
  learning_paths 增加 parent_path_id / version / is_active
  - parent_path_id: 重规划来源版本（新版本指向旧版本，形成链路）
  - version: 同一学生路径版本号，从 1 递增
  - is_active: 当前生效路径标记（待采纳新版本为 False）
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision: str = "008_learning_path_version"
down_revision: Union[str, None] = "007_cognitive_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "learning_paths",
        sa.Column(
            "parent_path_id",
            UUID(as_uuid=True),
            sa.ForeignKey("learning_paths.id", ondelete="SET NULL"),
            nullable=True,
            comment="父路径ID（重规划来源版本）",
        ),
    )
    op.create_index(
        "ix_learning_paths_parent_path_id",
        "learning_paths",
        ["parent_path_id"],
    )
    op.add_column(
        "learning_paths",
        sa.Column(
            "version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
            comment="路径版本号",
        ),
    )
    op.add_column(
        "learning_paths",
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
            comment="是否为当前生效路径",
        ),
    )
    op.create_index(
        "ix_learning_paths_is_active",
        "learning_paths",
        ["is_active"],
    )
    # 历史记录：一律标记为 version=1, is_active=True（基线版本）
    op.execute(
        "UPDATE learning_paths SET version = 1, is_active = TRUE "
        "WHERE version IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_learning_paths_is_active", table_name="learning_paths")
    op.drop_column("learning_paths", "is_active")
    op.drop_column("learning_paths", "version")
    op.drop_index("ix_learning_paths_parent_path_id", table_name="learning_paths")
    op.drop_column("learning_paths", "parent_path_id")
