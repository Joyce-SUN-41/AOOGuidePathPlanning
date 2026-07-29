"""项目启动前置引导脚本 — 所有 python 命令应先 source 本文件里的 setup_env()

处理两个问题：
1. 后端依赖安装到了 backend/.venv_pkgs/（避开全局权限冲突）
2. Windows 下沙盒 PYTHONPATH 注入方式不稳定，统一在 Python 里 sys.path 提前插入
"""

import os
import sys
import site
from pathlib import Path

BACKEND_DIR = Path(r"e:\AOOGuidePathPlanning\backend").resolve()
TARGET_PKGS = BACKEND_DIR / ".venv_pkgs"
FALLBACK_USER_SITE = Path(os.path.expandvars(r"%APPDATA%\Python\Python314\site-packages"))


def setup_env() -> None:
    """按优先级注入依赖搜索路径，同时确保能 import app.xxx"""

    # 1. 优先级最高：本地 target 目录（--target 安装的依赖）
    if TARGET_PKGS.exists():
        site.addsitedir(str(TARGET_PKGS))
        if str(TARGET_PKGS) not in sys.path:
            sys.path.insert(0, str(TARGET_PKGS))

    # 2. 用户级 site-packages（大部分全局依赖在这里）
    if FALLBACK_USER_SITE.exists():
        site.addsitedir(str(FALLBACK_USER_SITE))
        if str(FALLBACK_USER_SITE) not in sys.path:
            sys.path.insert(0, str(FALLBACK_USER_SITE))

    # 3. 后端源码根目录，确保 app.* 可导入
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    # 4. 让 pydantic-settings 能找到 backend/.env（默认 BASE_DIR.parent = backend/）
    os.chdir(BACKEND_DIR)


if __name__ == "__main__":
    setup_env()
    import asyncpg, redis, celery, alembic  # noqa: F401
    from jose import jwt  # noqa: F401
    from passlib.context import CryptContext  # noqa: F401
    from app.core.config import settings  # noqa: F401

    print("✅ setup_env() 环境注入成功")
    print(f"   .venv_pkgs 存在: {TARGET_PKGS.exists()}, 子目录数: {len(list(TARGET_PKGS.glob('*'))) if TARGET_PKGS.exists() else 0}")
    print(f"   DB:  {settings.DATABASE_URL.replace(settings.POSTGRES_PASSWORD, '***')}")
    print(f"   Redis: {settings.redis_url}")
