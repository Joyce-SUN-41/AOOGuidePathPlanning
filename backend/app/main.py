"""FastAPI 应用入口

启动: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text as sa_text

from app.api.v1.router import router as v1_router
from app.core.config import settings
from app.core.database import AsyncSessionLocal, check_db_connection
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import setup_logging
from app.core.security import get_password_hash
from app.middleware.rate_limit import RateLimitMiddleware
from app.models.user import User

logger = logging.getLogger(__name__)


async def ensure_demo_users():
    """确保 demo 用户存在数据库（首次启动自动创建）"""
    async with AsyncSessionLocal() as db:
        try:
            demo_users = [
                ("student_demo", "A9OGoP1DGixMM3_VvyzzTwJ07ggvhFSb", "学生Demo", "student"),
                ("teacher_demo", "A9OGoP1DGixMM3_VvyzzTwJ07ggvhFSb", "教师Demo", "teacher"),
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


async def ensure_seed_data():
    """确保种子数据（知识点、知识图谱、题库）存在数据库中"""
    try:
        from app.scripts.seed_data import (
            seed_knowledge_points, seed_knowledge_graph, seed_questions,
        )
        async with AsyncSessionLocal() as db:
            # 检查是否已有知识点数据
            result = await db.execute(sa_text("SELECT COUNT(*) FROM knowledge_points"))
            count = result.scalar()
            if count and count > 0:
                logger.info(
                    "Seed data already present (%d knowledge points), skipping", count
                )
                return

            logger.info("🌱 Initializing seed data (knowledge points + graph + questions)...")
            id_map = await seed_knowledge_points(db)
            if id_map:
                await seed_knowledge_graph(db, id_map)
                await seed_questions(db, id_map)
            logger.info(
                "✅ Seed data initialized: %d knowledge points, 20 questions",
                len(id_map),
            )
    except Exception as exc:
        logger.warning("Failed to seed knowledge data (may not exist yet): %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # ---- 启动时 ----
    setup_logging()
    logger.info("=" * 60)
    logger.info("App starting: %s v%s", settings.PROJECT_NAME, settings.VERSION)

    # 运行时配置校验 — 警告不安全默认值
    config_warnings = settings.validate_critical_settings()
    for w in config_warnings:
        logger.warning("⚠ CONFIG: %s", w)

    if await check_db_connection():
        logger.info("Database connection: OK")
        await ensure_demo_users()
        await ensure_seed_data()
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
    contact={
        "name": "燕麦智导开发团队",
        "url": "https://github.com/Joyce-SUN-41/AOOGuidePathPlanning",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    openapi_tags=[
        {"name": "Root", "description": "根路径与基础信息"},
        {"name": "Health", "description": "健康检查 / 就绪探针 / Prometheus 指标"},
        {"name": "Authentication", "description": "用户认证 — 登录 / 注册 / Token 刷新"},
        {"name": "Users", "description": "用户管理"},
        {"name": "Diagnosis", "description": "认知诊断 — 题库获取 / 答案提交 / 掌握度评估"},
        {"name": "Knowledge Points", "description": "知识点管理与知识图谱"},
        {"name": "Question Bank", "description": "题库管理 CRUD"},
        {"name": "AOO Optimization", "description": "AOO 燕麦动画优化算法引擎 — 路径生成 / 状态查询"},
        {"name": "RAG Knowledge Base", "description": "RAG 检索增强生成 — 文档索引 / 语义检索"},
        {"name": "Agent", "description": "讯飞星辰 Agent 对话 — 工具调用 / 多轮对话"},
        {"name": "Chat", "description": "智能问答 — 基于 RAG+LLM 的课程答疑"},
        {"name": "Teacher", "description": "教师仪表盘 — 班级概览 / 学情分析 / 预警"},
        {"name": "Learning Paths", "description": "学习路径 — 时间轴 / 甘特图 / 备选方案"},
        {"name": "Dashboard", "description": "学生学情看板 — 认知趋势 / 活动热力图 / AI 建议"},
    ],
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

# ---- 速率限制中间件 ----
app.add_middleware(
    RateLimitMiddleware,
    max_requests=120,       # 每分钟 120 次 (平均 2 req/s)
    window_seconds=60,
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
