#!/usr/bin/env python
"""本地开发环境一键检查与初始化

用途:
    在新机器上克隆项目后，快速确认本地环境是否就绪，并完成
    可自动化的初始化步骤（生成 .env、安装依赖、初始化演示数据）。

用法:
    # 只检查，不做任何改动（推荐先跑这个）
    python scripts/setup_local.py --check

    # 执行初始化（生成 .env + 安装依赖 + 创建演示用户）
    python scripts/setup_local.py

    # 跳过依赖安装（依赖已装好时更快）
    python scripts/setup_local.py --skip-deps

设计原则:
    - 幂等：重复执行不会破坏已有配置
    - 非破坏：不会覆盖已存在的 .env，不会删除任何数据
    - 失败即停：任一关键步骤失败会明确报错并给出修复建议
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

MIN_PYTHON = (3, 10)
MIN_NODE_MAJOR = 18


def _print_step(title: str) -> None:
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def _run(cmd: list[str], cwd: Path | None = None) -> bool:
    """执行命令，返回是否成功"""
    print(f"$ {' '.join(cmd)}")
    try:
        subprocess.run(cmd, cwd=cwd, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"[FAIL] 命令执行失败: {exc}")
        return False


# ---------------------------------------------------------------- 检查项


def check_python() -> bool:
    ok = sys.version_info >= MIN_PYTHON
    ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(f"[{'OK' if ok else 'FAIL'}] Python {ver} (需要 >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]})")
    return ok


def check_node() -> bool:
    node = shutil.which("node")
    if not node:
        print("[FAIL] 未找到 node，请安装 Node.js 18+")
        return False
    try:
        out = subprocess.run(
            [node, "--version"], capture_output=True, text=True, check=True
        ).stdout.strip()
        major = int(out.lstrip("v").split(".")[0])
        ok = major >= MIN_NODE_MAJOR
        print(f"[{'OK' if ok else 'FAIL'}] Node {out} (需要 >= v{MIN_NODE_MAJOR})")
        return ok
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] 无法解析 Node 版本: {exc}")
        return True


def check_env_file() -> bool:
    exists = (BACKEND_DIR / ".env").exists()
    print(f"[{'OK' if exists else 'MISS'}] backend/.env {'已存在' if exists else '不存在'}")
    return exists


def check_frontend_env() -> bool:
    dev = (PROJECT_ROOT / ".env.development").exists()
    prod = (PROJECT_ROOT / ".env.production").exists()
    print(f"[{'OK' if dev else 'MISS'}] .env.development")
    print(f"[{'OK' if prod else 'MISS'}] .env.production")
    return dev and prod


def check_services() -> bool:
    """检查 PostgreSQL / Redis 端口是否可连接（不阻断流程）"""
    import socket

    all_ok = True
    for name, host, port in (
        ("PostgreSQL", os.getenv("POSTGRES_HOST", "localhost"), int(os.getenv("POSTGRES_PORT", "5432"))),
        ("Redis", os.getenv("REDIS_HOST", "localhost"), int(os.getenv("REDIS_PORT", "6379"))),
    ):
        try:
            with socket.create_connection((host, port), timeout=2):
                print(f"[OK] {name} {host}:{port} 可连接")
        except OSError:
            print(f"[WARN] {name} {host}:{port} 无法连接 —— 可用 `docker compose up -d postgres redis` 启动")
            all_ok = False
    return all_ok


def run_checks() -> int:
    _print_step("环境检查")
    results = {
        "python": check_python(),
        "node": check_node(),
        "backend_env": check_env_file(),
        "frontend_env": check_frontend_env(),
    }
    check_services()  # 仅提示，不计入失败

    _print_step("检查结果")
    blocking = [k for k in ("python", "node") if not results[k]]
    if blocking:
        print(f"[FAIL] 关键依赖不满足: {', '.join(blocking)}")
        return 1
    if not results["backend_env"]:
        print("[TODO] 运行 `python scripts/env_bootstrap.py` 生成 backend/.env")
    print("[DONE] 基础环境检查通过")
    return 0


# ---------------------------------------------------------------- 初始化


def setup(skip_deps: bool) -> int:
    if run_checks() != 0:
        return 1

    # 1. 生成后端 .env
    _print_step("步骤 1/3 — 生成 backend/.env")
    if (BACKEND_DIR / ".env").exists():
        print("[SKIP] backend/.env 已存在，保持不变")
    else:
        if not _run([sys.executable, str(SCRIPTS_DIR / "env_bootstrap.py")]):
            return 1

    # 2. 安装依赖
    _print_step("步骤 2/3 — 安装依赖")
    if skip_deps:
        print("[SKIP] 已指定 --skip-deps")
    else:
        req = BACKEND_DIR / "requirements.txt"
        if req.exists():
            if not _run([sys.executable, "-m", "pip", "install", "-r", str(req)]):
                print("[WARN] 后端依赖安装失败，请手动重试")
        npm = shutil.which("npm")
        if npm and (PROJECT_ROOT / "package.json").exists():
            if not _run([npm, "install"], cwd=PROJECT_ROOT):
                print("[WARN] 前端依赖安装失败，请手动重试")

    # 3. 创建演示用户
    _print_step("步骤 3/3 — 创建演示用户")
    if not _run([sys.executable, str(SCRIPTS_DIR / "create_demo_users.py")]):
        print("[WARN] 演示用户创建失败（数据库可能未启动），可稍后手动执行")

    _print_step("完成")
    print("启动方式:")
    print("  后端: cd backend && uvicorn app.main:app --reload")
    print("  前端: npm run dev")
    print("  或全栈: docker compose up -d")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="本地开发环境一键检查与初始化")
    parser.add_argument("--check", action="store_true", help="仅检查，不做任何改动")
    parser.add_argument("--skip-deps", action="store_true", help="跳过依赖安装")
    args = parser.parse_args()

    if args.check:
        return run_checks()
    return setup(args.skip_deps)


if __name__ == "__main__":
    sys.exit(main())
