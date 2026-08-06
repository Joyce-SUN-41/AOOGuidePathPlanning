"""初始化完整数据库 Schema

Revision ID: 001
Revises: None
Create Date: 2026-07-27

动麦智导学习路径推荐系统 — 全部9张核心表
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建所有表"""

    # ---- 启用 uuid-ossp 扩展 ----
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ========================================================================
    # 1. users 用户表
    # ========================================================================
    op.create_table(
        "users",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            comment="用户唯一ID",
        ),
        sa.Column(
            "username",
            sa.String(50),
            nullable=False,
            comment="用户名",
        ),
        sa.Column(
            "email",
            sa.String(255),
            nullable=False,
            comment="邮箱",
        ),
        sa.Column(
            "hashed_password",
            sa.String(255),
            nullable=False,
            comment="加密密码",
        ),
        sa.Column(
            "role",
            sa.String(20),
            nullable=False,
            server_default="student",
            comment="角色: student | teacher",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
            comment="是否激活",
        ),
        sa.Column(
            "is_superuser",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
            comment="是否超级管理员",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="更新时间",
        ),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])

    # ---- updated_at 触发器 ----
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_users_updated_at
            BEFORE UPDATE ON users
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    """)

    # ========================================================================
    # 2. knowledge_points 知识点表
    # ========================================================================
    op.create_table(
        "knowledge_points",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            comment="知识点唯一ID",
        ),
        sa.Column(
            "name",
            sa.String(200),
            nullable=False,
            comment="知识点名称",
        ),
        sa.Column(
            "description",
            sa.Text(),
            comment="知识点描述",
        ),
        sa.Column(
            "subject",
            sa.String(100),
            nullable=False,
            comment="学科",
        ),
        sa.Column(
            "difficulty_level",
            sa.SmallInteger(),
            nullable=False,
            server_default="1",
            comment="难度: 1-5",
        ),
        sa.Column(
            "parent_id",
            UUID(as_uuid=True),
            nullable=True,
            comment="父知识点ID (层级结构)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="创建时间",
        ),
    )
    op.create_index("ix_kp_subject", "knowledge_points", ["subject"])
    op.create_index(
        "ix_kp_difficulty_level",
        "knowledge_points",
        ["difficulty_level"],
    )
    op.create_index("ix_kp_parent_id", "knowledge_points", ["parent_id"])
    op.create_foreign_key(
        "fk_kp_parent",
        "knowledge_points",
        "knowledge_points",
        ["parent_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ========================================================================
    # 3. knowledge_graph 知识图谱边表
    # ========================================================================
    op.create_table(
        "knowledge_graph",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            comment="边唯一ID",
        ),
        sa.Column(
            "source_kp_id",
            UUID(as_uuid=True),
            nullable=False,
            comment="前置知识点ID",
        ),
        sa.Column(
            "target_kp_id",
            UUID(as_uuid=True),
            nullable=False,
            comment="后置知识点ID",
        ),
        sa.Column(
            "relation_type",
            sa.String(30),
            nullable=False,
            server_default="prerequisite",
            comment="关系类型",
        ),
    )
    op.create_index(
        "ix_kg_source_kp_id", "knowledge_graph", ["source_kp_id"]
    )
    op.create_index(
        "ix_kg_target_kp_id", "knowledge_graph", ["target_kp_id"]
    )
    op.create_unique_constraint(
        "uq_knowledge_graph_edge",
        "knowledge_graph",
        ["source_kp_id", "target_kp_id"],
    )
    op.create_foreign_key(
        "fk_kg_source",
        "knowledge_graph",
        "knowledge_points",
        ["source_kp_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_kg_target",
        "knowledge_graph",
        "knowledge_points",
        ["target_kp_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ========================================================================
    # 4. student_knowledge 学生知识点掌握度表
    # ========================================================================
    op.create_table(
        "student_knowledge",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            comment="记录ID",
        ),
        sa.Column(
            "student_id",
            UUID(as_uuid=True),
            nullable=False,
            comment="学生用户ID",
        ),
        sa.Column(
            "kp_id",
            UUID(as_uuid=True),
            nullable=False,
            comment="知识点ID",
        ),
        sa.Column(
            "mastery_level",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="掌握度: 0.0-1.0",
        ),
        sa.Column(
            "last_assessed_at",
            sa.DateTime(timezone=True),
            comment="最近评估时间",
        ),
    )
    op.create_index(
        "ix_sk_student_id", "student_knowledge", ["student_id"]
    )
    op.create_index("ix_sk_kp_id", "student_knowledge", ["kp_id"])
    op.create_index(
        "ix_sk_mastery_level", "student_knowledge", ["mastery_level"]
    )
    op.create_index(
        "ix_sk_last_assessed", "student_knowledge", ["last_assessed_at"]
    )
    op.create_unique_constraint(
        "uq_student_knowledge",
        "student_knowledge",
        ["student_id", "kp_id"],
    )
    op.create_foreign_key(
        "fk_sk_student",
        "student_knowledge",
        "users",
        ["student_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_sk_kp",
        "student_knowledge",
        "knowledge_points",
        ["kp_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ========================================================================
    # 5. learning_paths 学习路径表
    # ========================================================================
    op.create_table(
        "learning_paths",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            comment="路径ID",
        ),
        sa.Column(
            "student_id",
            UUID(as_uuid=True),
            nullable=False,
            comment="学生用户ID",
        ),
        sa.Column(
            "path_data",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="路径结构数据 (JSONB)",
        ),
        sa.Column(
            "total_duration",
            sa.Integer(),
            comment="预计总时长 (分钟)",
        ),
        sa.Column(
            "estimated_completion_days",
            sa.Integer(),
            comment="预计完成天数",
        ),
        sa.Column(
            "fitness_score",
            sa.Float(),
            comment="AOO 适应度得分",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="创建时间",
        ),
    )
    op.create_index(
        "ix_lp_student_id", "learning_paths", ["student_id"]
    )
    op.create_index(
        "ix_lp_created_at", "learning_paths", ["created_at"]
    )
    op.create_index(
        "ix_lp_fitness_score", "learning_paths", ["fitness_score"]
    )
    op.create_foreign_key(
        "fk_lp_student",
        "learning_paths",
        "users",
        ["student_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ========================================================================
    # 6. path_tasks 路径任务表
    # ========================================================================
    op.create_table(
        "path_tasks",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            comment="任务ID",
        ),
        sa.Column(
            "path_id",
            UUID(as_uuid=True),
            nullable=False,
            comment="所属路径ID",
        ),
        sa.Column(
            "kp_id",
            UUID(as_uuid=True),
            nullable=False,
            comment="对应知识点ID",
        ),
        sa.Column(
            "day_index",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="第几天 (从1开始)",
        ),
        sa.Column(
            "order_index",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="当天任务顺序",
        ),
        sa.Column(
            "task_type",
            sa.String(20),
            nullable=False,
            server_default="reading",
            comment="任务类型: video | quiz | reading | project",
        ),
        sa.Column(
            "estimated_minutes",
            sa.Integer(),
            nullable=False,
            server_default="15",
            comment="预估分钟数",
        ),
        sa.Column(
            "completed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
            comment="是否完成",
        ),
    )
    op.create_index("ix_pt_path_id", "path_tasks", ["path_id"])
    op.create_index("ix_pt_kp_id", "path_tasks", ["kp_id"])
    op.create_index(
        "ix_pt_day_order",
        "path_tasks",
        ["path_id", "day_index", "order_index"],
    )
    op.create_index("ix_pt_completed", "path_tasks", ["completed"])
    op.create_foreign_key(
        "fk_pt_path",
        "path_tasks",
        "learning_paths",
        ["path_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_pt_kp",
        "path_tasks",
        "knowledge_points",
        ["kp_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ========================================================================
    # 7. cognitive_load_records 认知负荷记录表
    # ========================================================================
    op.create_table(
        "cognitive_load_records",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            comment="记录ID",
        ),
        sa.Column(
            "student_id",
            UUID(as_uuid=True),
            nullable=False,
            comment="学生用户ID",
        ),
        sa.Column(
            "load_score",
            sa.Float(),
            nullable=False,
            comment="负荷评分: 0.0-1.0",
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="记录时间",
        ),
        sa.Column(
            "context",
            sa.String(30),
            nullable=False,
            server_default="study",
            comment="上下文: diagnostic | study",
        ),
    )
    op.create_index(
        "ix_clr_student_id", "cognitive_load_records", ["student_id"]
    )
    op.create_index(
        "ix_clr_recorded_at", "cognitive_load_records", ["recorded_at"]
    )
    op.create_index(
        "ix_clr_student_time",
        "cognitive_load_records",
        ["student_id", "recorded_at"],
    )
    op.create_foreign_key(
        "fk_clr_student",
        "cognitive_load_records",
        "users",
        ["student_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ========================================================================
    # 8. chat_history 问答历史表
    # ========================================================================
    op.create_table(
        "chat_history",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            comment="问答ID",
        ),
        sa.Column(
            "student_id",
            UUID(as_uuid=True),
            nullable=False,
            comment="学生用户ID",
        ),
        sa.Column(
            "question",
            sa.Text(),
            nullable=False,
            comment="用户问题",
        ),
        sa.Column(
            "answer",
            sa.Text(),
            nullable=False,
            comment="系统回答",
        ),
        sa.Column(
            "sources",
            JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            comment="引用溯源 [{kp_id, content, score}]",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="创建时间",
        ),
    )
    op.create_index(
        "ix_ch_student_id", "chat_history", ["student_id"]
    )
    op.create_index(
        "ix_ch_created_at", "chat_history", ["created_at"]
    )
    op.create_foreign_key(
        "fk_ch_student",
        "chat_history",
        "users",
        ["student_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ========================================================================
    # 9. aoo_optimization_logs AOO寻优日志表
    # ========================================================================
    op.create_table(
        "aoo_optimization_logs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            comment="日志ID",
        ),
        sa.Column(
            "student_id",
            UUID(as_uuid=True),
            nullable=False,
            comment="学生用户ID",
        ),
        sa.Column(
            "iteration",
            sa.Integer(),
            nullable=False,
            comment="迭代轮次",
        ),
        sa.Column(
            "best_fitness",
            sa.Float(),
            comment="最佳适应度",
        ),
        sa.Column(
            "avg_fitness",
            sa.Float(),
            comment="平均适应度",
        ),
        sa.Column(
            "diversity",
            sa.Float(),
            comment="种群多样性",
        ),
        sa.Column(
            "convergence_data",
            JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            comment="收敛详细数据 (JSONB)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="创建时间",
        ),
    )
    op.create_index(
        "ix_aol_student_id", "aoo_optimization_logs", ["student_id"]
    )
    op.create_index(
        "ix_aol_created_at", "aoo_optimization_logs", ["created_at"]
    )
    op.create_index(
        "ix_aol_student_iteration",
        "aoo_optimization_logs",
        ["student_id", "iteration"],
    )
    op.create_foreign_key(
        "fk_aol_student",
        "aoo_optimization_logs",
        "users",
        ["student_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """回滚所有表"""
    op.drop_table("aoo_optimization_logs")
    op.drop_table("chat_history")
    op.drop_table("cognitive_load_records")
    op.drop_table("path_tasks")
    op.drop_table("learning_paths")
    op.drop_table("student_knowledge")
    op.drop_table("knowledge_graph")
    op.drop_table("knowledge_points")
    op.execute("DROP TRIGGER IF EXISTS trg_users_updated_at ON users")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")
    op.drop_table("users")
