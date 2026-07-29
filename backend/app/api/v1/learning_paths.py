"""学习路径 API — 获取 / 切换 / 历史查询"""

import uuid
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.learning_path import LearningPath
from app.models.user import User
from app.schemas.common import ResponseBase

router = APIRouter()


# ═══════════ 辅助：DB 模型 → 前端兼容 JSON ═══════════


def _path_to_response(record: LearningPath) -> Dict[str, Any]:
    """将 DB LearningPath 记录转为前端 LearningPath 接口格式"""
    data = record.path_data or {}

    return {
        "id": str(record.id),
        "taskId": str(record.id),
        "diagnosisId": data.get("diagnosisId", ""),
        "userId": str(record.student_id),
        "createdAt": record.created_at.isoformat() if record.created_at else "",
        "totalDays": data.get("totalDays", 0),
        "totalTasks": data.get("totalTasks", 0),
        "totalEstimatedHours": data.get("totalEstimatedHours", 0),
        "difficultyCurve": data.get("difficultyCurve", []),
        "dailyTasks": data.get("dailyTasks", []),
        "metadata": {
            "algorithm": data.get("metadata", {}).get("algorithm", "AOO"),
            "optimizationScore": data.get("metadata", {}).get(
                "optimizationScore", record.fitness_score or 0
            ),
            "generationTime": data.get("metadata", {}).get("generationTime", 0),
        },
    }


# ═══════════ 静态路径必须放在参数化路径前面 ═══════════


@router.get(
    "/current",
    response_model=ResponseBase,
    summary="获取当前活跃学习路径",
)
async def get_current_path(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前学生最新的学习路径"""
    result = await db.execute(
        select(LearningPath)
        .where(LearningPath.student_id == current_user.id)
        .order_by(desc(LearningPath.created_at))
        .limit(1)
    )
    record = result.scalar_one_or_none()

    if not record:
        return ResponseBase(code=200, message="暂无学习路径", data=None)

    return ResponseBase(data=_path_to_response(record))


@router.get(
    "/history",
    response_model=ResponseBase,
    summary="获取学习路径历史列表",
)
async def get_path_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前学生的学习路径历史列表"""
    count_result = await db.execute(
        select(func.count(LearningPath.id)).where(
            LearningPath.student_id == current_user.id
        )
    )
    total = count_result.scalar() or 0

    records_result = await db.execute(
        select(LearningPath)
        .where(LearningPath.student_id == current_user.id)
        .order_by(desc(LearningPath.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    records = records_result.scalars().all()

    items = [_path_to_response(r) for r in records]

    return ResponseBase(data={"items": items, "total": total})


@router.post(
    "/select",
    response_model=ResponseBase,
    summary="激活指定路径方案",
)
async def select_path(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """切换到备选路径方案"""
    path_id = body.get("path_id", "")
    if not path_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="path_id 不能为空",
        )

    try:
        uid = uuid.UUID(path_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的路径 ID 格式",
        )

    result = await db.execute(
        select(LearningPath).where(LearningPath.id == uid)
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="路径不存在")

    return ResponseBase(
        message="已激活所选方案",
        data={"activePathId": str(record.id)},
    )


# ═══════════ 参数化路径放最后 ═══════════


@router.get(
    "/{path_id}",
    response_model=ResponseBase,
    summary="获取指定学习路径详情",
)
async def get_path_detail(
    path_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取指定 ID 的学习路径"""
    try:
        uid = uuid.UUID(path_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的路径 ID 格式",
        )

    result = await db.execute(
        select(LearningPath).where(LearningPath.id == uid)
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="学习路径不存在",
        )

    if str(record.student_id) != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权查看他人的学习路径",
        )

    return ResponseBase(data=_path_to_response(record))


@router.delete(
    "/{path_id}",
    response_model=ResponseBase,
    summary="删除学习路径",
)
async def delete_path(
    path_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除指定学习路径"""
    try:
        uid = uuid.UUID(path_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的路径 ID 格式",
        )

    result = await db.execute(
        select(LearningPath).where(LearningPath.id == uid)
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="路径不存在")

    if str(record.student_id) != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权操作他人的学习路径",
        )

    await db.delete(record)
    await db.commit()

    return ResponseBase(message="路径已删除")
