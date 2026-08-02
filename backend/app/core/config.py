"""核心配置模块 — 基于 pydantic-settings，自动从 .env 文件加载"""

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录 (backend/)
BASE_DIR = Path(__file__).resolve().parent.parent

_log = logging.getLogger(__name__)


class Settings(BaseSettings):
    """应用配置，所有变量从 .env 文件自动注入"""

    model_config = SettingsConfigDict(
        # BASE_DIR 指向 app/，.env 位于其上一级 backend/
        env_file=str(BASE_DIR.parent / ".env"),
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

    # ---- Demo 用户 (⚠ 默认关闭，避免生产环境自动创建后门账号) ----
    # 仅在开发/演示环境显式置为 true 时，启动才会自动创建 student_demo/teacher_demo
    ENABLE_DEMO_USERS: bool = False

    @field_validator("DEBUG", mode="before")
    @classmethod
    def _parse_debug(cls, v):
        # 容错：允许大小写/前后空格/1|0 等写法，避免 .env 手抖导致后端启动崩溃
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        s = str(v).strip().lower()
        return s in ("1", "true", "yes", "on", "t", "y")

    @field_validator("ENABLE_DEMO_USERS", mode="before")
    @classmethod
    def _parse_demo_users(cls, v):
        # 容错：与 DEBUG 保持一致的解析策略
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        s = str(v).strip().lower()
        return s in ("1", "true", "yes", "on", "t", "y")

    # ---- JWT 认证 (⚠ SECRET_KEY 必须通过环境变量设置，生产环境不能使用默认值) ----
    SECRET_KEY: str = "change-me-prod-env-var-at-least-32-chars!!"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ---- PostgreSQL (⚠ 生产环境通过环境变量覆盖) ----
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "aoo_user"
    POSTGRES_PASSWORD: str = "changeme"
    POSTGRES_DB: str = "aoo_guide_path"
    DATABASE_URL: str = ""  # 空则动态拼接，或有值直接使用

    @property
    def effective_database_url(self) -> str:
        """如果 DATABASE_URL 为空，动态拼接；否则直接使用"""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def sync_database_url(self) -> str:
        """同步数据库URL，供 Alembic 使用"""
        url = self.effective_database_url
        return url.replace("+asyncpg", "").replace(
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

    # ---- 讯飞星火助手 WebSocket API ----
    # XF_APP_ID: 应用 APPID (控制台 → 应用管理)
    # XF_API_KEY: API Key (控制台 → 星火助手 → 接口鉴权参数)
    # XF_API_SECRET: API Secret (控制台 → 星火助手 → 接口鉴权参数)
    # XF_ASSISTANT_ID: 助手 ID (控制台 → 星火助手 → 助手 ID)
    # XF_API_URL: WebSocket 地址 (可选，默认从 assistant_id 拼接)
    # XF_MODEL: 模型 domain，generalv3 或 general
    XF_APP_ID: str = ""
    XF_API_KEY: str = ""
    XF_API_SECRET: str = ""
    XF_ASSISTANT_ID: str = ""
    XF_API_URL: str = ""
    XF_MODEL: str = "generalv3"

    # ---- 讯飞星火 HTTP REST API (OpenAI 兼容) ----
    # XF_API_PASSWORD: REST API 的 APIPassword (控制台 → 对应模型版本页面获取)
    #   与 WebSocket 的 api_key/api_secret 不同，需单独获取
    XF_API_PASSWORD: str = ""

    # ---- 讯飞星辰 Agent ----
    XINGCHEN_AGENT_API_URL: str = ""
    XINGCHEN_AGENT_API_KEY: str = ""
    XINGCHEN_AGENT_FLOW_ID: str = ""
    XINGCHEN_SESSION_TTL: int = 3600

    # ---- RAG 知识库 ----
    RAG_PERSIST_DIR: str = "./data/vector_store"
    RAG_CHUNK_SIZE: int = 800
    RAG_CHUNK_OVERLAP: int = 150
    RAG_SIMILARITY_THRESHOLD: float = 0.5
    RAG_TOP_K: int = 5
    RAG_MAX_CONTEXT_CHARS: int = 4000

    # ---- 对话即诊断 / 认知画像 (CSP) ----
    # CHAT_PROFILE_ENABLED: 问答信号是否参与 AOO 输入 (P3 总开关，可秒回滚)
    # CHAT_PROFILE_LAMBDA: 问答影响强度系数 λ ∈ [0,1]，初期 0.3
    # CHAT_PROFILE_MAX_DELTA: 单知识点相对诊断基线的最大偏移 δ_max
    # CHAT_PROFILE_PRIOR: 无任何基线时的先验掌握度 (向其回归，而非归零)
    # CHAT_KP_FUZZY_THRESHOLD: kp_name → kp_id 模糊匹配相似度阈值
    # CHAT_AUTO_OPTIMIZE_COOLDOWN: 自动重规划最小间隔(秒)，防连续追问并发刷 AOO
    CHAT_PROFILE_ENABLED: bool = True
    CHAT_PROFILE_LAMBDA: float = 0.3
    CHAT_PROFILE_MAX_DELTA: float = 0.25
    CHAT_PROFILE_PRIOR: float = 0.5
    CHAT_KP_FUZZY_THRESHOLD: float = 0.85
    CHAT_AUTO_OPTIMIZE_COOLDOWN: int = 600

    # ---- 日志 ----
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "console"  # json | console
    LOG_FILE_PATH: str = "./logs/app.log"

    # ---- CORS ----
    CORS_ORIGINS: str = '["http://localhost:5173","http://localhost:3000"]'

    # ---- 受信任代理 (用于安全解析 X-Forwarded-For / X-Real-IP) ----
    # 仅当请求来自受信任代理时才采信这些头，防止客户端伪造 XFF 绕过限流/IP 审计。
    # 默认包含私有网段与常见 Docker 桥接网关；生产可在 .env 追加真实边界代理 IP/CIDR。
    TRUSTED_PROXIES: str = "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.1,::1"

    @property
    def cors_origins_list(self) -> List[str]:
        """解析 CORS_ORIGINS JSON 字符串为列表"""
        try:
            return json.loads(self.CORS_ORIGINS)
        except (json.JSONDecodeError, TypeError):
            return ["http://localhost:5173", "http://localhost:3000"]

    @property
    def trusted_proxies_list(self) -> List[str]:
        """解析 TRUSTED_PROXIES 逗号分隔列表"""
        if not self.TRUSTED_PROXIES:
            return []
        return [p.strip() for p in self.TRUSTED_PROXIES.split(",") if p.strip()]

    def validate_critical_settings(self) -> List[str]:
        """运行时校验关键配置是否使用不安全默认值，返回警告列表"""
        warnings: List[str] = []
        unsafe_secret_keys = {
            "change-me-prod-env-var-at-least-32-chars!!",
            "changeme", "secret", "test", "dev",
        }
        if self.SECRET_KEY in unsafe_secret_keys or len(self.SECRET_KEY) < 16:
            warnings.append(
                "SECRET_KEY 使用了不安全默认值或长度不足(<16)，"
                "生产环境请立即更换为至少 32 字符的随机字符串"
            )
        if self.POSTGRES_PASSWORD in ("changeme", "password", "postgres", ""):
            warnings.append(
                "POSTGRES_PASSWORD 使用了不安全默认值，生产环境请更换"
            )
        if self.APP_PORT == 8000 and not self.DEBUG:
            _log.info("运行在默认端口 8000 (非 DEBUG 模式)")
        return warnings


@lru_cache()
def get_settings() -> Settings:
    """获取单例配置实例 (使用 lru_cache 避免重复实例化)"""
    return Settings()


settings = get_settings()
