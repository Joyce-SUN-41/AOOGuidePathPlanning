"""用户管理接口"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_superuser, get_current_user
from app.core.database import get_db
from app.core.security import get_password_hash
from app.models.user import User
from app.schemas.common import PaginatedResponse, ResponseBase
from app.schemas.user import UserOut, UserUpdate

router = APIRouter()


@router.get("/", response_model=PaginatedResponse[UserOut], summary="获取用户列表")
async def list_users(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(None, description="按用户名/昵称模糊搜索"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_superuser),
):
    """获取分页用户列表 (仅超级管理员，支持关键字搜索)"""
    # 搜索过滤条件
    filters = None
    if search:
        like = f"%{search.strip()}%"
        filters = or_(User.username.ilike(like), User.nickname.ilike(like))

    # 总数
    count_stmt = select(func.count(User.id))
    if filters is not None:
        count_stmt = count_stmt.where(filters)
    total = (await db.execute(count_stmt)).scalar() or 0

    # 分页查询
    offset = (page - 1) * page_size
    query = select(User).order_by(User.created_at.desc())
    if filters is not None:
        query = query.where(filters)
    result = await db.execute(query.offset(offset).limit(page_size))
    users = result.scalars().all()

    pages = (total + page_size - 1) // page_size if total > 0 else 0
    return PaginatedResponse(
        items=list(users),
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/{user_id}", response_model=UserOut, summary="获取单个用户")
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """根据 ID 获取用户详情"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return user


@router.put("/{user_id}", response_model=UserOut, summary="更新用户")
async def update_user(
    user_id: uuid.UUID,
    user_in: UserUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_superuser),
):
    """更新用户信息 (仅超级管理员)"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    update_data = user_in.model_dump(exclude_unset=True)
    if "password" in update_data:
        update_data["hashed_password"] = get_password_hash(update_data.pop("password"))

    for field, value in update_data.items():
        setattr(user, field, value)

    await db.flush()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", summary="删除用户")
async def delete_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_superuser),
):
    """删除用户 (仅超级管理员)"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    await db.delete(user)
    await db.flush()
    return ResponseBase(message="用户已删除")
