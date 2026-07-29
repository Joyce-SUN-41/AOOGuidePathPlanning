"""添加缺失的时间戳字段 + knowledge_points.metadata 列

Revision ID: 004_add_timestamps_and_metadata
Revises: 003_question_bank
Create Date: 2026-07-28

修复模型与迁移脚本的一致性问题:
  - knowledge_points: 新增 updated_at, metadata(JSONB)
  - knowledge_graph: 新增 created_at, updated_at
  - student_knowledge: 新增 created_at, updated_at
  - learning_paths: 新增 updated_at
  - path_tasks: 新增 created_at, updated_at
  - cognitive_load_records: 新增 created_at, updated_at
  - chat_history: 新增 updated_at
  - aoo_optimization_logs: 新增 updated_at
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "004_add_timestamps_and_metadata"
down_revision: Union[str, None] = "003_question_bank"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- knowledge_points ----
    op.add_column(
        "knowledge_points",
        sa.Column(
            "metadata",
            JSONB,
            nullable=True,
            comment="扩展元数据",
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "knowledge_points",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="更新时间",
        ),
    )
    op.execute("""
        CREATE TRIGGER trg_knowledge_points_updated_at
            BEFORE UPDATE ON knowledge_points
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    """)

    # ---- knowledge_graph ----
    op.add_column(
        "knowledge_graph",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="创建时间",
        ),
    )
    op.add_column(
        "knowledge_graph",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="更新时间",
        ),
    )
    op.execute("""
        CREATE TRIGGER trg_knowledge_graph_updated_at
            BEFORE UPDATE ON knowledge_graph
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    """)

    # ---- student_knowledge ----
    op.add_column(
        "student_knowledge",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="创建时间",
        ),
    )
    op.add_column(
        "student_knowledge",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="更新时间",
        ),
    )
    op.execute("""
        CREATE TRIGGER trg_student_knowledge_updated_at
            BEFORE UPDATE ON student_knowledge
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    """)

    # ---- learning_paths ----
    op.add_column(
        "learning_paths",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="更新时间",
        ),
    )
    op.execute("""
        CREATE TRIGGER trg_learning_paths_updated_at
            BEFORE UPDATE ON learning_paths
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    """)

    # ---- path_tasks ----
    op.add_column(
        "path_tasks",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="创建时间",
        ),
    )
    op.add_column(
        "path_tasks",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="更新时间",
        ),
    )
    op.execute("""
        CREATE TRIGGER trg_path_tasks_updated_at
            BEFORE UPDATE ON path_tasks
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    """)

    # ---- cognitive_load_records ----
    op.add_column(
        "cognitive_load_records",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="创建时间",
        ),
    )
    op.add_column(
        "cognitive_load_records",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="更新时间",
        ),
    )
    op.execute("""
        CREATE TRIGGER trg_cognitive_load_records_updated_at
            BEFORE UPDATE ON cognitive_load_records
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    """)

    # ---- chat_history ----
    op.add_column(
        "chat_history",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="更新时间",
        ),
    )
    op.execute("""
        CREATE TRIGGER trg_chat_history_updated_at
            BEFORE UPDATE ON chat_history
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    """)

    # ---- aoo_optimization_logs ----
    op.add_column(
        "aoo_optimization_logs",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="更新时间",
        ),
    )
    op.execute("""
        CREATE TRIGGER trg_aoo_optimization_logs_updated_at
            BEFORE UPDATE ON aoo_optimization_logs
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    """)


def downgrade() -> None:
    # ---- aoo_optimization_logs ----
    op.execute("DROP TRIGGER IF EXISTS trg_aoo_optimization_logs_updated_at ON aoo_optimization_logs")
    op.drop_column("aoo_optimization_logs", "updated_at")

    # ---- chat_history ----
    op.execute("DROP TRIGGER IF EXISTS trg_chat_history_updated_at ON chat_history")
    op.drop_column("chat_history", "updated_at")

    # ---- cognitive_load_records ----
    op.execute("DROP TRIGGER IF EXISTS trg_cognitive_load_records_updated_at ON cognitive_load_records")
    op.drop_column("cognitive_load_records", "updated_at")
    op.drop_column("cognitive_load_records", "created_at")

    # ---- path_tasks ----
    op.execute("DROP TRIGGER IF EXISTS trg_path_tasks_updated_at ON path_tasks")
    op.drop_column("path_tasks", "updated_at")
    op.drop_column("path_tasks", "created_at")

    # ---- learning_paths ----
    op.execute("DROP TRIGGER IF EXISTS trg_learning_paths_updated_at ON learning_paths")
    op.drop_column("learning_paths", "updated_at")

    # ---- student_knowledge ----
    op.execute("DROP TRIGGER IF EXISTS trg_student_knowledge_updated_at ON student_knowledge")
    op.drop_column("student_knowledge", "updated_at")
    op.drop_column("student_knowledge", "created_at")

    # ---- knowledge_graph ----
    op.execute("DROP TRIGGER IF EXISTS trg_knowledge_graph_updated_at ON knowledge_graph")
    op.drop_column("knowledge_graph", "updated_at")
    op.drop_column("knowledge_graph", "created_at")

    # ---- knowledge_points ----
    op.execute("DROP TRIGGER IF EXISTS trg_knowledge_points_updated_at ON knowledge_points")
    op.drop_column("knowledge_points", "updated_at")
    op.drop_column("knowledge_points", "metadata")
