"""添加 diagnosis_records 诊断记录表

Revision ID: 002_diagnosis
Revises: 001_initial_schema
Create Date: 2026-07-27

用于存储认知诊断测验的完整结果
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers
revision: str = "002_diagnosis"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 diagnosis_records 表"""
    op.create_table(
        "diagnosis_records",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            comment="诊断记录唯一 ID",
        ),
        sa.Column(
            "student_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            comment="学生用户 ID",
        ),
        sa.Column(
            "subject",
            sa.String(100),
            nullable=False,
            server_default="mathematics",
            comment="学科",
        ),
        sa.Column(
            "grade",
            sa.String(50),
            nullable=False,
            server_default="",
            comment="年级",
        ),
        sa.Column(
            "answers",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
            comment="完整答题记录",
        ),
        sa.Column(
            "mastery_levels",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="各知识点掌握度",
        ),
        sa.Column(
            "cognitive_load",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="认知负荷画像",
        ),
        sa.Column(
            "cognitive_load_index",
            sa.Float,
            nullable=False,
            server_default="0.0",
            comment="综合认知负荷指数 0-1",
        ),
        sa.Column(
            "weak_points",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
            comment="薄弱点列表",
        ),
        sa.Column(
            "radar_data",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="雷达图数据",
        ),
        sa.Column(
            "overall_score",
            sa.Float,
            nullable=False,
            server_default="0.0",
            comment="综合评分 0-100",
        ),
        sa.Column(
            "learning_style",
            sa.String(100),
            nullable=False,
            server_default="未评估",
            comment="推断的学习风格标签",
        ),
        sa.Column(
            "summary",
            sa.Text,
            nullable=False,
            server_default="",
            comment="AI 诊断摘要",
        ),
        sa.Column(
            "total_questions",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="总题数",
        ),
        sa.Column(
            "correct_count",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="答对题数",
        ),
        sa.Column(
            "average_time_spent",
            sa.Float,
            nullable=False,
            server_default="0.0",
            comment="平均答题时间(秒)",
        ),
        sa.Column(
            "expected_average_time",
            sa.Float,
            nullable=False,
            server_default="15.0",
            comment="预期平均答题时间(秒)",
        ),
        sa.Column(
            "consecutive_errors",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="最大连续错误数",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="创建时间",
        ),
    )

    # 创建索引
    op.create_index(
        "ix_diagnosis_records_student_id",
        "diagnosis_records",
        ["student_id"],
    )
    op.create_index(
        "ix_diagnosis_records_subject",
        "diagnosis_records",
        ["subject"],
    )
    op.create_index(
        "ix_diagnosis_records_created_at",
        "diagnosis_records",
        ["created_at"],
    )


def downgrade() -> None:
    """删除 diagnosis_records 表"""
    op.drop_index(
        "ix_diagnosis_records_created_at",
        table_name="diagnosis_records",
    )
    op.drop_index(
        "ix_diagnosis_records_subject",
        table_name="diagnosis_records",
    )
    op.drop_index(
        "ix_diagnosis_records_student_id",
        table_name="diagnosis_records",
    )
    op.drop_table("diagnosis_records")
