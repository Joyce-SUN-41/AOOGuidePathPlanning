"""数据库数据字典自动生成器

从 SQLAlchemy ORM 模型自动提取字段信息，生成 Markdown 格式的数据字典文档。

运行方式:
    cd backend && python scripts/generate_db_dictionary.py > ../docs/db-dictionary.md
"""

import inspect
import sys
from pathlib import Path
from typing import get_type_hints

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def generate():
    """生成数据字典"""
    from sqlalchemy import Column, ForeignKey
    from sqlalchemy.types import (
        Integer, BigInteger, String, Text, Boolean, Float,
        DateTime, Date, Enum, JSON, UUID,
    )

    # 导入所有模型
    from app.models import (
        user, knowledge_point, knowledge_graph,
        question, diagnosis, learning_path, path_task,
        student_knowledge, cognitive_load_record,
        chat_history, aoo_optimization_log,
    )

    models = [
        user.User,
        knowledge_point.KnowledgePoint,
        knowledge_graph.KnowledgeGraphEdge,
        question.Question,
        diagnosis.DiagnosisRecord,
        learning_path.LearningPath,
        path_task.PathTask,
        student_knowledge.StudentKnowledge,
        cognitive_load_record.CognitiveLoadRecord,
        chat_history.ChatHistory,
        aoo_optimization_log.AOOOptimizationLog,
    ]

    type_name_map = {
        Integer: "INTEGER",
        BigInteger: "BIGINT",
        String: "VARCHAR",
        Text: "TEXT",
        Boolean: "BOOLEAN",
        Float: "FLOAT",
        DateTime: "TIMESTAMP",
        Date: "DATE",
        Enum: "VARCHAR",
        JSON: "JSONB",
        UUID: "UUID",
    }

    lines = [
        "# 数据库数据字典",
        "",
        f"> 自动生成于 {Path(__file__).stat().st_mtime}",
        "",
        "---",
        "",
        "## 表概览",
        "",
        "| # | 表名 | 说明 |",
        "|---|---|---|",
    ]

    for i, model in enumerate(models, 1):
        doc = inspect.getdoc(model) or ""
        first_line = doc.split("\n")[0].strip() if doc else "—"
        lines.append(f"| {i} | `{model.__tablename__}` | {first_line} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    for model in models:
        table_name = model.__tablename__
        doc = inspect.getdoc(model) or ""
        lines.append(f"## `{table_name}`")
        lines.append("")
        if doc:
            lines.append(f"{doc}")
            lines.append("")

        lines.append("| 列名 | 类型 | 约束 | 说明 |")
        lines.append("|---|---|---|---|")

        for col in model.__table__.columns:
            col_type = type(col.type)
            sql_type = type_name_map.get(col_type, col.type.__class__.__name__)

            constraints = []
            if col.primary_key:
                constraints.append("PK")
            if col.foreign_keys:
                fks = ", ".join(str(fk.column) for fk in col.foreign_keys)
                constraints.append(f"FK → {fks}")
            if not col.nullable:
                constraints.append("NOT NULL")
            if col.unique:
                constraints.append("UNIQUE")
            if col.default and col.default.arg is not None:
                constraints.append(f"DEFAULT {col.default.arg}")
            if col.server_default:
                constraints.append(f"DEFAULT {col.server_default.arg}")

            comment = col.comment or "—"
            constraint_str = ", ".join(constraints) if constraints else "—"

            lines.append(
                f"| `{col.name}` | {sql_type}"
                f"{f'({col.type.length})' if hasattr(col.type, 'length') and col.type.length else ''}"
                f" | {constraint_str} | {comment} |"
            )

        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    print(generate())
