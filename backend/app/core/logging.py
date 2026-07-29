"""日志系统配置 — 支持 JSON 格式 (生产) 和 console 格式 (开发)"""

import logging
import sys
from pathlib import Path

from app.core.config import settings


def setup_logging() -> None:
    """初始化全局日志配置"""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    # 清除已有 handler，避免重复添加
    root_logger.handlers.clear()

    if settings.LOG_FORMAT == "json":
        # JSON 格式 (生产环境友好，易于日志采集)
        formatter = logging.Formatter(
            '{"time": "%(asctime)s", "level": "%(levelname)s", '
            '"module": "%(name)s", "message": "%(message)s"}',
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    else:
        # 控制台友好格式 (开发环境)
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)-8s %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # ---- 控制台输出 ----
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # ---- 文件输出 ----
    log_path = Path(settings.LOG_FILE_PATH)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # 降低第三方库日志噪点
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    root_logger.info("Logging system initialized | level=%s", settings.LOG_LEVEL)
