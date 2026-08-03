"""添加 avatar 和 phone 列

Revision ID: 006
Revises: 005_add_nickname_and_email_nullable
Create Date: 2026-08-02

变更:
  1. users 表新增 avatar (TEXT, nullable) — 头像 Base64
  2. users 表新增 phone (VARCHAR 20, nullable) — 手机号
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006_add_avatar_and_phone"
down_revision: Union[str, None] = "005_add_nickname_and_email_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "avatar",
            sa.Text(),
            nullable=True,
            comment="头像 (Base64 data URL)",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "phone",
            sa.String(20),
            nullable=True,
            comment="手机号",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "phone")
    op.drop_column("users", "avatar")
