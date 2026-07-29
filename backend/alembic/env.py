"""Alembic 迁移环境配置 — 异步支持"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import settings
from app.core.database import Base

# 导入所有模型，确保 Base.metadata 包含完整表结构
from app.models.user import User  # noqa: F401
from app.models.knowledge_point import KnowledgePoint  # noqa: F401
from app.models.knowledge_graph import KnowledgeGraphEdge  # noqa: F401
from app.models.student_knowledge import StudentKnowledge  # noqa: F401
from app.models.learning_path import LearningPath  # noqa: F401
from app.models.path_task import PathTask  # noqa: F401
from app.models.cognitive_load_record import CognitiveLoadRecord  # noqa: F401
from app.models.chat_history import ChatHistory  # noqa: F401
from app.models.aoo_optimization_log import AOOOptimizationLog  # noqa: F401
from app.models.diagnosis import DiagnosisRecord  # noqa: F401
from app.models.question import Question  # noqa: F401

# Alembic Config 对象
config = context.config

# 设置日志
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 设置目标 metadata
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：生成 SQL 脚本而不连接数据库"""
    url = settings.sync_database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """异步模式：连接数据库执行迁移"""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = settings.DATABASE_URL

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """在线模式：连接数据库执行迁移"""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
