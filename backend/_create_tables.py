"""快速建表脚本：跳过 Alembic，直接用 SQLAlchemy metadata.create_all"""

import asyncio
import sys
from pathlib import Path

# 将 backend 目录加入 sys.path（兼容本地和 Docker 环境）
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import engine, Base

# 把所有模型 import 进来，确保 Base.metadata 里能登记所有表
from app.models.user import User
from app.models.knowledge_point import KnowledgePoint
from app.models.knowledge_graph import KnowledgeGraphEdge
from app.models.student_knowledge import StudentKnowledge
from app.models.learning_path import LearningPath
from app.models.path_task import PathTask
from app.models.cognitive_load_record import CognitiveLoadRecord
from app.models.chat_history import ChatHistory
from app.models.aoo_optimization_log import AOOOptimizationLog
from app.models.diagnosis import DiagnosisRecord
from app.models.question import Question

TABLE_NAMES = [
    "users",
    "knowledge_points",
    "knowledge_graph",
    "student_knowledge",
    "learning_paths",
    "path_tasks",
    "cognitive_load_records",
    "chat_history",
    "aoo_optimization_logs",
    "diagnosis_records",
    "questions",
]


async def main() -> None:
    print("🚀 开始执行 create_all（幂等安全）...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ create_all 结束，开始验证表数量...")

    async with engine.connect() as conn:
        rows = await conn.execute(
            __import__("sqlalchemy").text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
        )
        created = sorted([r[0] for r in rows.fetchall()])

    expected = sorted(TABLE_NAMES)
    missing = [t for t in expected if t not in created]
    extra = [t for t in created if t not in expected]

    print(f"   需要表数:  {len(expected)}")
    print(f"   实际存在表: {len(created)}")
    print(f"   已创建表: {created}")

    if missing:
        print(f"❌ 缺失表: {missing}")
        sys.exit(1)

    if extra:
        print(f"ℹ️  额外表(alembic_version等, 正常): {[t for t in extra if t != 'alembic_version']}")

    print("✅ 11 张核心表全部存在！迁移完成")


if __name__ == "__main__":
    asyncio.run(main())
