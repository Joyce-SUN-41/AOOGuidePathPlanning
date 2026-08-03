#!/usr/bin/env python
"""创建 / 重置演示用户

用途:
    后端 `main.py` 的 lifespan 会在首次启动时自动创建 demo 用户，
    本脚本提供**手动**创建与密码重置能力，适用于:
      - 数据库被清空后快速恢复演示账号
      - 演示前重置密码
      - CI / 部署流水线中显式初始化

用法:
    # 使用默认演示密码创建（已存在则跳过）
    python scripts/create_demo_users.py

    # 指定密码
    python scripts/create_demo_users.py --password 'YourStrongPass123'

    # 已存在时强制重置密码
    python scripts/create_demo_users.py --force

    # 从环境变量 DEMO_PASSWORD 读取密码
    DEMO_PASSWORD=xxx python scripts/create_demo_users.py

注意:
    本脚本只做「新增 / 更新密码」，不会删除任何用户数据。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# 让脚本可以直接运行：把 backend/ 加入 import 路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# 与 main.py lifespan 中保持一致的默认演示密码
DEFAULT_DEMO_PASSWORD = "A9OGoP1DGixMM3_VvyzzTwJ07ggvhFSb"

DEMO_USERS = [
    # (username, nickname, role)
    ("student_demo", "学生Demo", "student"),
    ("teacher_demo", "教师Demo", "teacher"),
]


async def create_demo_users(password: str, force: bool) -> int:
    """创建或更新演示用户，返回退出码"""
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal, check_db_connection
    from app.core.security import get_password_hash
    from app.models.user import User

    if not await check_db_connection():
        print("[ERROR] 数据库连接失败，请检查 PostgreSQL 是否启动、配置是否正确")
        return 1

    created, updated, skipped = 0, 0, 0

    async with AsyncSessionLocal() as db:
        try:
            for username, nickname, role in DEMO_USERS:
                result = await db.execute(select(User).where(User.username == username))
                existing = result.scalar_one_or_none()

                if existing:
                    if force:
                        existing.hashed_password = get_password_hash(password)
                        existing.is_active = True
                        updated += 1
                        print(f"[UPDATE] 已重置密码: {username} ({role})")
                    else:
                        skipped += 1
                        print(f"[SKIP]   已存在，未改动: {username} ({role})")
                    continue

                db.add(
                    User(
                        username=username,
                        nickname=nickname,
                        hashed_password=get_password_hash(password),
                        role=role,
                        is_active=True,
                    )
                )
                created += 1
                print(f"[CREATE] 已创建: {username} ({role})")

            await db.commit()
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            print(f"[ERROR] 操作失败，已回滚: {exc}")
            return 1

    print("-" * 50)
    print(f"完成 — 新建 {created} / 更新 {updated} / 跳过 {skipped}")
    if created or updated:
        print("提示: 演示密码不要用于生产环境，部署前请通过 --password 指定强密码")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="创建 / 重置演示用户")
    parser.add_argument(
        "--password",
        default=os.getenv("DEMO_PASSWORD", DEFAULT_DEMO_PASSWORD),
        help="演示账号密码（默认读取环境变量 DEMO_PASSWORD）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="用户已存在时强制重置其密码",
    )
    args = parser.parse_args()

    if len(args.password) < 8:
        print("[ERROR] 密码长度至少 8 位")
        return 1

    return asyncio.run(create_demo_users(args.password, args.force))


if __name__ == "__main__":
    raise SystemExit(main())
