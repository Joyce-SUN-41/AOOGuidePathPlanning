"""集成测试公共夹具 (pytest fixtures)

设计目标 —— 让 API 集成测试能在 CI 中「零外部依赖」运行：

1. **不连 PostgreSQL / Redis**：用内存版 SQLite (aiosqlite) 建库，
   通过 ``app.dependency_overrides`` 覆盖 ``get_db``。
2. **不触发 lifespan**：``main.lifespan`` 会做 DB 探活 + 种子数据写入，
   在 CI 里会连不上 PG 并拖慢启动。因此使用 ASGITransport 直接驱动 app，
   不走 ``LifespanManager``，startup 逻辑自然被跳过。
3. **鉴权可控**：提供 ``auth_client`` 夹具直接覆盖 ``get_current_user``，
   避免测试依赖真实登录链路（登录链路另有独立用例覆盖）。

注意：这些测试验证的是 **API 契约**（路由存在性、鉴权、状态码、响应包裹格式），
不是业务算法正确性 —— 算法正确性由 tests/test_aoo_engine.py 的单元测试覆盖。
"""

from __future__ import annotations

import os
import uuid
from typing import AsyncGenerator

# ── 必须在导入 app 之前设置环境变量 ─────────────────────────
# app.core.config 在 import 期读取环境，晚设置就不生效了。
# app.core.database 在模块导入期就会 create_async_engine(...)，且传入了
# pool_size / max_overflow —— 这两个参数 SQLite 方言不接受。因此这里给一个
# **PostgreSQL 形态的 URL** 让模块导入期的引擎能被构造出来（不会真正连接，
# 因为从不对它发起请求）；测试实际使用的是 db_engine 夹具里的 SQLite 引擎，
# 通过 dependency_overrides 注入，二者互不干扰。
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1:5432/test_db"
)
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-only-not-for-production")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

# ── 让 PostgreSQL 专有类型能在 SQLite 上建表 ───────────────────
# 模型层用了 JSONB / UUID（PG 方言），SQLite 无法编译这些类型。
# 注册编译规则把它们降级为 SQLite 支持的等价类型，使 create_all 可用。
# 仅影响测试进程，不改动任何业务模型定义。


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):  # noqa: ANN001, ANN202
    return "JSON"


@compiles(PG_UUID, "sqlite")
def _compile_uuid_sqlite(type_, compiler, **kw):  # noqa: ANN001, ANN202
    return "CHAR(36)"


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def db_engine():
    """每个测试一个独立的内存库。

    StaticPool + 单一连接，保证 ``:memory:`` 在多次 session 间是同一个库。
    """
    from app.core.database import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # 导入所有模型，确保 Base.metadata 收集齐全部表定义
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    maker = async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    """未认证的 HTTP 客户端（用于验证公开端点与 401 行为）。"""
    from app.core.database import get_db
    from app.main import app

    maker = async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession):
    """在测试库里插入一个真实 User 行。"""
    from app.models.user import User

    user = User(
        id=uuid.uuid4(),
        username="pytest_user",
        nickname="集成测试用户",
        email="pytest@example.com",
        hashed_password="not-a-real-hash",
        role="student",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_client(db_engine, test_user) -> AsyncGenerator[AsyncClient, None]:
    """已认证的 HTTP 客户端 —— 直接覆盖 get_current_user 依赖。"""
    from app.api.deps import get_current_user
    from app.core.database import get_db
    from app.main import app

    maker = async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def _override_current_user():
        return test_user

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
