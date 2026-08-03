#!/usr/bin/env python
"""环境变量引导 — 生成 backend/.env 并填充安全的随机密钥

用途:
    从 `backend/.env.example` 生成 `backend/.env`，并自动为
    SECRET_KEY / 数据库密码等敏感项生成强随机值，避免使用
    示例文件里的 "change-me-*" 占位值。

用法:
    # 生成 backend/.env（若已存在则拒绝覆盖）
    python scripts/env_bootstrap.py

    # 覆盖已存在的 .env（会先备份为 .env.bak）
    python scripts/env_bootstrap.py --force

    # 只检查现有 .env 是否仍含占位值，不做任何写入
    python scripts/env_bootstrap.py --check

安全说明:
    - 生成的 .env 已被 .gitignore 忽略，不会进入版本库
    - 覆盖前会自动备份，不会静默丢失原有配置
"""

from __future__ import annotations

import argparse
import re
import secrets
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
ENV_EXAMPLE = BACKEND_DIR / ".env.example"
ENV_FILE = BACKEND_DIR / ".env"

# 需要自动生成随机值的键 -> 生成器
SECRET_KEYS = {
    "SECRET_KEY": lambda: secrets.token_urlsafe(48),
    "POSTGRES_PASSWORD": lambda: secrets.token_urlsafe(24),
}

# 视为「未填写」的占位值特征
PLACEHOLDER_PATTERN = re.compile(r"change[-_]?me|your[-_]?|xxx+|<.*>", re.IGNORECASE)


def _parse_env(text: str) -> dict[str, str]:
    """解析 .env 文本为 key -> value 字典（忽略注释与空行）"""
    result: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        result[key.strip()] = value.strip()
    return result


def check_env() -> int:
    """检查现有 .env 中是否还存在占位值"""
    if not ENV_FILE.exists():
        print(f"[WARN] 未找到 {ENV_FILE}")
        print("       运行 `python scripts/env_bootstrap.py` 生成")
        return 1

    values = _parse_env(ENV_FILE.read_text(encoding="utf-8"))
    problems: list[str] = []

    for key in SECRET_KEYS:
        value = values.get(key, "")
        if not value or PLACEHOLDER_PATTERN.search(value):
            problems.append(f"{key} 仍是占位值或为空")

    secret = values.get("SECRET_KEY", "")
    if secret and len(secret) < 32:
        problems.append("SECRET_KEY 长度不足 32 位")

    if problems:
        print(f"[FAIL] {ENV_FILE} 存在 {len(problems)} 处问题：")
        for p in problems:
            print(f"  - {p}")
        return 1

    print(f"[OK] {ENV_FILE} 关键项检查通过")
    return 0


def bootstrap(force: bool) -> int:
    """从 .env.example 生成 .env 并注入随机密钥"""
    if not ENV_EXAMPLE.exists():
        print(f"[ERROR] 模板不存在: {ENV_EXAMPLE}")
        return 1

    if ENV_FILE.exists() and not force:
        print(f"[SKIP] {ENV_FILE} 已存在。如需重新生成请加 --force（会自动备份）")
        return 0

    if ENV_FILE.exists():
        backup = ENV_FILE.with_suffix(".env.bak")
        shutil.copy2(ENV_FILE, backup)
        print(f"[BACKUP] 原文件已备份到 {backup}")

    generated: dict[str, str] = {k: gen() for k, gen in SECRET_KEYS.items()}

    out_lines: list[str] = []
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in generated:
                out_lines.append(f"{key}={generated[key]}")
                continue
        out_lines.append(line)

    text = "\n".join(out_lines) + "\n"

    # 同步 DATABASE_URL 里的密码，保持与 POSTGRES_PASSWORD 一致
    new_pwd = generated.get("POSTGRES_PASSWORD")
    if new_pwd:
        text = re.sub(
            r"(postgresql\+asyncpg://[^:]+:)[^@]*(@)",
            lambda m: f"{m.group(1)}{new_pwd}{m.group(2)}",
            text,
        )

    ENV_FILE.write_text(text, encoding="utf-8")
    print(f"[OK] 已生成 {ENV_FILE}")
    print(f"     已自动填充随机值: {', '.join(generated)}")
    print("提示: 讯飞星火等第三方密钥仍需手动填写 (XF_APP_ID / XF_API_KEY / ...)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 backend/.env 并填充随机密钥")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的 .env（自动备份）")
    parser.add_argument("--check", action="store_true", help="仅检查，不写入任何文件")
    args = parser.parse_args()

    if args.check:
        return check_env()
    return bootstrap(args.force)


if __name__ == "__main__":
    sys.exit(main())
