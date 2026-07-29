"""添加 nickname 列，并允许 email 为空

Revision ID: 005
Revises: 004_add_timestamps_and_metadata
Create Date: 2026-07-28

变更:
  1. users 表新增 nickname (VARCHAR 50, nullable)
  2. users.email 改为允许 NULL（前端 email 为选填）
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005_add_nickname_and_email_nullable"
down_revision: Union[str, None] = "004_add_timestamps_and_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 添加 nickname 列
    op.add_column(
        "users",
        sa.Column(
            "nickname",
            sa.String(50),
            nullable=True,
            comment="昵称（显示名称）",
        ),
    )

    # 2. 允许 email 为空
    op.alter_column("users", "email", nullable=True)


def downgrade() -> None:
    # 先还原 email 非空（如果有 NULL 值会失败，需要手动处理）
    op.alter_column("users", "email", nullable=False)

    # 删除 nickname 列
    op.drop_column("users", "nickname")
