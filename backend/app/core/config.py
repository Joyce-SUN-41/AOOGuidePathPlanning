"""核心配置模块 — 基于 pydantic-settings，自动从 .env 文件加载"""

import json
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录 (backend/)
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """应用配置，所有变量从 .env 文件自动注入"""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- 应用 ----
    PROJECT_NAME: str = "AOO Guide Path Planning"
    PROJECT_DESCRIPTION: str = "AOO算法引导路径规划系统"
    VERSION: str = "0.1.0"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DEBUG: bool = False

    # ---- JWT 认证 ----
    SECRET_KEY: str = "change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ---- PostgreSQL ----
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "aoo_user"
    POSTGRES_PASSWORD: str = "aoo_password_2024"
    POSTGRES_DB: str = "aoo_guide_path"
    DATABASE_URL: str = (
        "postgresql+asyncpg://aoo_user:aoo_password_2024@localhost:5432/aoo_guide_path"
    )

    @property
    def sync_database_url(self) -> str:
        """同步数据库URL，供 Alembic 使用"""
        return self.DATABASE_URL.replace("+asyncpg", "").replace(
            "postgresql+asyncpg", "postgresql"
        )

    # ---- Redis ----
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""
    REDIS_URL: str = ""

    @property
    def redis_url(self) -> str:
        if self.REDIS_URL:
            return self.REDIS_URL
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # ---- Celery ----
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # ---- 讯飞星火 ----
    XF_APP_ID: str = ""
    XF_API_KEY: str = ""
    XF_API_SECRET: str = ""
    XF_API_URL: str = "wss://spark-api.xf-yun.com/v3.5/chat"
    XF_MODEL: str = "spark-x"

    # ---- 讯飞星辰 Agent ----
    XINGCHEN_AGENT_API_URL: str = ""
    XINGCHEN_AGENT_API_KEY: str = ""
    XINGCHEN_AGENT_FLOW_ID: str = ""
    XINGCHEN_SESSION_TTL: int = 3600

    # ---- RAG 知识库 ----
    RAG_PERSIST_DIR: str = "./data/chroma_db"
    RAG_CHUNK_SIZE: int = 800
    RAG_CHUNK_OVERLAP: int = 150
    RAG_SIMILARITY_THRESHOLD: float = 0.5
    RAG_TOP_K: int = 5
    RAG_MAX_CONTEXT_CHARS: int = 4000

    # ---- 日志 ----
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "console"  # json | console
    LOG_FILE_PATH: str = "./logs/app.log"

    # ---- CORS ----
    CORS_ORIGINS: str = '["http://localhost:5173","http://localhost:3000"]'

    @property
    def cors_origins_list(self) -> List[str]:
        """解析 CORS_ORIGINS JSON 字符串为列表"""
        try:
            return json.loads(self.CORS_ORIGINS)
        except (json.JSONDecodeError, TypeError):
            return ["http://localhost:5173", "http://localhost:3000"]


@lru_cache()
def get_settings() -> Settings:
    """获取单例配置实例 (使用 lru_cache 避免重复实例化)"""
    return Settings()


settings = get_settings()
