"""认证接口 — 登录 / 注册 / Token 刷新"""

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, login_rate_limit
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.models.user import User
from app.schemas.common import ResponseBase
from app.schemas.token import AuthResponse, LoginRequest, Token, UserInfoResponse
from app.schemas.user import UserCreate, UserOut, UserUpdate

router = APIRouter()

logger = logging.getLogger(__name__)


def _build_user_info(user: User) -> UserInfoResponse:
    """将 User ORM 对象转换为前端需要的 UserInfoResponse 格式"""
    return UserInfoResponse(
        id=str(user.id),
        username=user.username,
        nickname=user.nickname or user.username,
        email=user.email,
        phone=getattr(user, "phone", "") or "",
        avatar=getattr(user, "avatar", "") or "",
        role=user.role,
        status=1 if user.is_active else 0,
        createTime=user.created_at.isoformat() if user.created_at else "",
    )


@router.post(
    "/login",
    response_model=ResponseBase[AuthResponse],
    summary="用户登录",
)
async def login(
    request: LoginRequest,
    http_request: Request = Depends(login_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """使用用户名和密码登录，返回 access + refresh token 和用户信息"""
    result = await db.execute(select(User).where(User.username == request.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
        )

    token = create_access_token(subject=str(user.id))
    refresh = create_refresh_token(subject=str(user.id))

    return ResponseBase(
        code=200,
        message="登录成功",
        data=AuthResponse(
            token=token,
            refreshToken=refresh,
            userInfo=_build_user_info(user),
        ),
    )


@router.post(
    "/register",
    response_model=ResponseBase[AuthResponse],
    status_code=status.HTTP_201_CREATED,
    summary="用户注册",
)
async def register(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """注册新用户，成功后自动登录并返回 token + 用户信息"""
    # 检查用户名是否已存在
    result = await db.execute(select(User).where(User.username == user_in.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已存在",
        )

    # 检查邮箱是否已存在（仅当提供了邮箱时）
    if user_in.email:
        result = await db.execute(select(User).where(User.email == user_in.email))
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="邮箱已被注册",
            )

    user = User(
        username=user_in.username,
        nickname=user_in.nickname or user_in.username,
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        role=user_in.role or "student",
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    # 注册成功，自动签发 token
    token = create_access_token(subject=str(user.id))
    refresh = create_refresh_token(subject=str(user.id))

    return ResponseBase(
        code=200,
        message="注册成功",
        data=AuthResponse(
            token=token,
            refreshToken=refresh,
            userInfo=_build_user_info(user),
        ),
    )


@router.post("/refresh", response_model=ResponseBase[Token], summary="刷新 Token")
async def refresh_token(
    refresh_token: str = Body(..., embed=True, description="refresh_token 值"),
    db: AsyncSession = Depends(get_db),
):
    """使用 refresh_token 换取新的 access_token（参数通过 JSON body 传递）"""
    payload = decode_token(refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌",
        )

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被禁用",
        )

    return ResponseBase(data=Token(
        access_token=create_access_token(subject=str(user.id)),
        refresh_token=create_refresh_token(subject=str(user.id)),
    ))


@router.get("/me", response_model=ResponseBase[UserInfoResponse], summary="获取当前用户信息")
async def get_me(current_user: User = Depends(get_current_user)):
    """返回当前登录用户的详细信息"""
    return ResponseBase(data=_build_user_info(current_user))


@router.post("/logout", response_model=ResponseBase, summary="退出登录")
async def logout(
    current_user: User = Depends(get_current_user),
):
    """退出登录（无状态 JWT 场景下的幂等注销点）。

    当前鉴权为无状态 JWT，服务端不维护会话黑名单，因此本端点不做实质失效处理，
    仅返回 200 供前端确认注销链路已闭合。令牌的实际失效由前端清除本地存储完成。
    保留该端点是为了让前端 userApi.logout 的调用不再指向不存在的路由（404），
    避免静默噪声并维持「前端调用 ↔ 后端端点」的一一对应。
    """
    # best-effort 审计：仅记录注销动作，不影响响应
    logger.info("用户注销: user_id=%s", current_user.id)
    return ResponseBase(message="已退出登录")


@router.put("/me", response_model=ResponseBase[UserInfoResponse], summary="更新当前用户资料")
async def update_me(
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新当前登录用户的昵称/邮箱/手机号/头像"""
    update_data = body.model_dump(exclude_unset=True, exclude={"username", "password", "role", "is_active"})
    if not update_data:
        raise HTTPException(status_code=400, detail="没有提供要更新的字段")
    for key, value in update_data.items():
        setattr(current_user, key, value)
    await db.commit()
    await db.refresh(current_user)
    return ResponseBase(data=_build_user_info(current_user))
