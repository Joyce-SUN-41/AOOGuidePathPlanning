"""FastAPI 应用入口

启动: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.v1.router import router as v1_router
from app.core.config import settings
from app.core.database import AsyncSessionLocal, check_db_connection
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import setup_logging
from app.core.security import get_password_hash
from app.models.user import User

logger = logging.getLogger(__name__)


async def ensure_demo_users():
    """确保 demo 用户存在数据库（首次启动自动创建）"""
    async with AsyncSessionLocal() as db:
        try:
            demo_users = [
                ("student_demo", "123456", "学生Demo", "student"),
                ("teacher_demo", "123456", "教师Demo", "teacher"),
            ]

            for username, password, nickname, role in demo_users:
                result = await db.execute(
                    select(User).where(User.username == username)
                )
                existing = result.scalar_one_or_none()
                if existing:
                    logger.info("Demo user already exists: %s", username)
                    continue

                user = User(
                    username=username,
                    nickname=nickname,
                    hashed_password=get_password_hash(password),
                    role=role,
                    is_active=True,
                )
                db.add(user)
                await db.flush()
                logger.info("Demo user created: %s (%s)", username, role)

            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.warning("Failed to create demo users: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # ---- 启动时 ----
    setup_logging()
    logger.info("=" * 60)
    logger.info("App starting: %s v%s", settings.PROJECT_NAME, settings.VERSION)

    if await check_db_connection():
        logger.info("Database connection: OK")
        await ensure_demo_users()
    else:
        logger.warning("Database connection: FAILED (check PostgreSQL)")

    logger.info("CORS origins: %s", settings.cors_origins_list)
    logger.info("=" * 60)

    yield

    # ---- 关闭时 ----
    logger.info("App shutting down...")


# ---- 创建 FastAPI 实例 ----
app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ---- CORS 中间件 ----
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "Content-Disposition"],
)

# ---- 注册路由 ----
app.include_router(v1_router)
register_exception_handlers(app)


# ---- 根路径 ----
@app.get("/", tags=["Root"])
async def root():
    """API 根路径"""
    return {
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs": "/docs",
        "health": "/api/v1/health",
    }
