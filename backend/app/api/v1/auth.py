"""认证接口 — 登录 / 注册 / Token 刷新"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
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
from app.schemas.user import UserCreate, UserOut

router = APIRouter()


def _build_user_info(user: User) -> UserInfoResponse:
    """将 User ORM 对象转换为前端需要的 UserInfoResponse 格式"""
    return UserInfoResponse(
        id=str(user.id),
        username=user.username,
        nickname=user.nickname or user.username,
        email=user.email,
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
            userInfo=_build_user_info(user),
        ),
    )


@router.post("/refresh", response_model=Token, summary="刷新 Token")
async def refresh_token(
    refresh_token: str,
    db: AsyncSession = Depends(get_db),
):
    """使用 refresh_token 换取新的 access_token"""
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

    return Token(
        access_token=create_access_token(subject=str(user.id)),
        refresh_token=create_refresh_token(subject=str(user.id)),
    )


@router.get("/me", response_model=UserOut, summary="获取当前用户信息")
async def get_me(current_user: User = Depends(get_current_user)):
    """返回当前登录用户的详细信息"""
    return current_user
