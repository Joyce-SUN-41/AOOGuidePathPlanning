# -*- coding: utf-8 -*-
"""本地开发一键 bootstrap — 所有 python 命令统一通过 python.exe setup_local.py 执行

解决问题：pypi.org SSL 访问失败，依赖通过清华源 `pip install --target backend/.venv_pkgs` 安装
"""
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
TARGET_PKGS = BACKEND_DIR / ".venv_pkgs"
USER_SITE = Path.home() / "AppData/Roaming/Python/Python314/site-packages"

# 按顺序注入（优先级从高到低）
for _p in [str(TARGET_PKGS), str(BACKEND_DIR), str(USER_SITE)]:
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

# 工作目录固定 backend/，pydantic-settings 才能正确读取 .env
os.chdir(BACKEND_DIR)

if __name__ == "__main__":
    # 先 import 验证
    import asyncpg, redis, celery, alembic, dotenv, bcrypt, pypdf
    from jose import jwt
    from passlib.context import CryptContext
    from app.core.config import settings

    print("✅ bootstrap 环境注入成功！")
    print(f"   sys.path 前3项: {sys.path[:3]}")
    print(f"   Postgres 连接: {settings.effective_database_url.replace(settings.POSTGRES_PASSWORD, '***')}")
    print(f"   Redis 连接:    {settings.redis_url}")

    # 第二个参数 onwards 作为子命令执行（类似 python -m）
    if len(sys.argv) > 1:
        import subprocess

        cmd = [sys.executable] + sys.argv[1:]
        env = os.environ.copy()
        old_pp = env.get("PYTHONPATH", "")
        parts = [p for p in [str(TARGET_PKGS), str(BACKEND_DIR), old_pp] if p]
        env["PYTHONPATH"] = os.pathsep.join(parts)
        print(f"\n▶  执行子命令: {' '.join(cmd)}")
        sys.exit(subprocess.call(cmd, env=env, cwd=BACKEND_DIR))
