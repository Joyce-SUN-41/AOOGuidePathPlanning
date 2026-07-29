"""种子数据初始化脚本

运行方式:
  cd backend
  python -m app.scripts.seed_data

或通过 FastAPI CLI:
  注册为管理命令后: python -m app.scripts.seed_data --clear

插入内容:
  1. 知识点 (knowledge_points) — 11 个 AI 导论知识点 (含 layer/tags)
  2. 知识图谱边 (knowledge_graph) — 12 条前置依赖关系
  3. 题库 (questions) — 20 道 AI 导论选择题

幂等性: 重复运行不会产生重复数据 (ON CONFLICT DO NOTHING)
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# 数据文件
KP_FILE = DATA_DIR / "knowledge_points.json"
QB_FILE = DATA_DIR / "question_bank.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_data")


async def seed_knowledge_points(db: AsyncSession) -> dict:
    """插入知识点，返回 {_id: 实际UUID} 映射表"""
    if not KP_FILE.exists():
        logger.error(f"知识点数据文件不存在: {KP_FILE}")
        return {}

    with open(KP_FILE, "r", encoding="utf-8") as f:
        kp_list = json.load(f)

    id_map: dict = {}
    for kp in kp_list:
        kp_id = kp["_id"]
        result = await db.execute(
            text(
                """
                INSERT INTO knowledge_points (id, name, description, subject, difficulty_level, layer, tags)
                VALUES (
                    gen_random_uuid(), :name, :description, :subject, :difficulty_level, :layer,
                    CAST(:tags AS jsonb)
                )
                ON CONFLICT DO NOTHING
                RETURNING id
                """
            ),
            {
                "name": kp["name"],
                "description": kp["description"],
                "subject": kp["subject"],
                "difficulty_level": kp["difficulty_level"],
                "layer": kp["layer"],
                "tags": json.dumps(kp["tags"]),
            },
        )
        row = result.fetchone()
        if row:
            actual_id = str(row[0])
            id_map[kp_id] = actual_id
            logger.info(f"  ✅ 知识点: {kp['name']} ({kp['layer']})")
        else:
            # 已存在，查询已有 ID
            r2 = await db.execute(
                text("SELECT id FROM knowledge_points WHERE name = :name"),
                {"name": kp["name"]},
            )
            existing = r2.fetchone()
            if existing:
                id_map[kp_id] = str(existing[0])
                logger.info(f"  ⏭️ 知识点已存在: {kp['name']}")

    await db.commit()
    logger.info(f"知识点初始化完成: {len(id_map)} 个")
    return id_map


async def seed_knowledge_graph(db: AsyncSession, id_map: dict):
    """根据 knowledge_points.json 的 prerequisites 建立前置依赖边"""
    if not KP_FILE.exists():
        return

    with open(KP_FILE, "r", encoding="utf-8") as f:
        kp_list = json.load(f)

    edge_count = 0
    for kp in kp_list:
        target_id = id_map.get(kp["_id"])
        if not target_id:
            continue
        for prereq_id in kp.get("prerequisites", []):
            source_id = id_map.get(prereq_id)
            if not source_id:
                logger.warning(f"  ⚠️ 前置知识点不存在: {prereq_id} (→ {kp['_id']})")
                continue
            result = await db.execute(
                text(
                    """
                    INSERT INTO knowledge_graph (id, source_kp_id, target_kp_id, relation_type)
                    VALUES (gen_random_uuid(), CAST(:source AS uuid), CAST(:target AS uuid), 'prerequisite')
                    ON CONFLICT (source_kp_id, target_kp_id) DO NOTHING
                    RETURNING id
                    """
                ),
                {"source": source_id, "target": target_id},
            )
            if result.fetchone():
                edge_count += 1
                logger.info(
                    f"  🔗 边: {prereq_id} → {kp['_id']} "
                    f"({kp_list[int(prereq_id.split('_')[2])-1]['name'] if prereq_id.startswith('kp_ai_') else prereq_id} → {kp['name']})"
                )

    await db.commit()
    logger.info(f"知识图谱边初始化完成: {edge_count} 条")


async def seed_questions(db: AsyncSession, id_map: dict):
    """插入题库题目 (通过 knowledge_points._id → 实际 UUID 映射)"""
    if not QB_FILE.exists():
        logger.error(f"题库数据文件不存在: {QB_FILE}")
        return

    with open(QB_FILE, "r", encoding="utf-8") as f:
        q_list = json.load(f)

    count = 0
    for q in q_list:
        # 将 kp_ids (_id 格式) 转为实际 UUID
        mapped_ids = [id_map.get(kpid) for kpid in q["kp_ids"]]
        mapped_ids = [x for x in mapped_ids if x is not None]
        if not mapped_ids:
            logger.warning(f"  ⚠️ 题目 {q['_id']} 无有效知识点关联，跳过")
            continue

        result = await db.execute(
            text(
                """
                INSERT INTO questions (
                    id, code, kp_ids, subject, difficulty, type, title,
                    options, correct_option_id, expected_time_sec, explanation, is_active
                )
                VALUES (
                    gen_random_uuid(), :code, CAST(:kp_ids AS jsonb), :subject,
                    :difficulty, :type, :title, CAST(:options AS jsonb),
                    :correct_option_id, :expected_time_sec, :explanation, TRUE
                )
                ON CONFLICT (code) DO NOTHING
                RETURNING id
                """
            ),
            {
                "code": q["_id"],
                "kp_ids": json.dumps(mapped_ids),
                "subject": "人工智能导论",
                "difficulty": q["difficulty"],
                "type": q["type"],
                "title": q["title"],
                "options": json.dumps(q["options"]),
                "correct_option_id": q["correct_option_id"],
                "expected_time_sec": int(q["expected_time_sec"]),
                "explanation": q.get("explanation", ""),
            },
        )
        if result.fetchone():
            count += 1
            logger.info(f"  📝 题目: {q['_id']} — {q['title'][:30]}... (难度:{q['difficulty']})")

    await db.commit()
    logger.info(f"题库初始化完成: {count} 道题")


async def clear_seed_data(db: AsyncSession):
    """清空种子数据 (按依赖顺序)"""
    logger.warning("⚠️  正在清空种子数据...")
    await db.execute(text("DELETE FROM questions"))
    await db.execute(text("DELETE FROM knowledge_graph"))
    await db.execute(text("DELETE FROM knowledge_points"))
    await db.commit()
    logger.info("种子数据已清空")


async def main():
    """主入口"""
    from app.core.database import AsyncSessionLocal

    clear_mode = "--clear" in sys.argv

    async with AsyncSessionLocal() as db:
        try:
            if clear_mode:
                await clear_seed_data(db)

            logger.info("=" * 60)
            logger.info("🌱 开始初始化种子数据...")

            # 1. 知识点
            id_map = await seed_knowledge_points(db)

            # 2. 知识图谱边
            if id_map:
                await seed_knowledge_graph(db, id_map)
            else:
                logger.warning("跳过了知识图谱初始化: 无有效知识点")

            # 3. 题库
            if id_map:
                await seed_questions(db, id_map)
            else:
                logger.warning("跳过了题库初始化: 无有效知识点")

            logger.info("=" * 60)
            logger.info("🎉 种子数据初始化完成!")

            await db.commit()
        except Exception:
            await db.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(main())
