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


def _alternatives_to_response(raw_alts: Any) -> list:
    """备选路径 snake_case → camelCase。

    DB 中每条结构为::

        {"path_type", "days", "total_days", "total_tasks",
         "total_estimated_hours", "fitness"}

    前端 store 的 ``_transformAlternativePath`` 同时兼容两种命名，
    但统一转成 camelCase 可避免歧义，并补上稳定的 ``id``。
    """
    if not isinstance(raw_alts, list):
        return []

    result = []
    for alt in raw_alts:
        if not isinstance(alt, dict):
            continue
        path_type = alt.get("path_type") or alt.get("pathType") or "balanced"
        result.append({
            "id": f"alt-{path_type}",
            "pathType": path_type,
            "days": alt.get("days") or [],
            "totalDays": alt.get("total_days", alt.get("totalDays", 0)),
            "totalTasks": alt.get("total_tasks", alt.get("totalTasks", 0)),
            "totalEstimatedHours": alt.get(
                "total_estimated_hours", alt.get("totalEstimatedHours", 0)
            ),
            "fitness": alt.get("fitness", 0),
        })
    return result


def _convergence_to_response(raw_conv: Any) -> Dict[str, Any] | None:
    """收敛回放数据 snake_case → camelCase。

    没有 ``iterations`` 就返回 None，让前端 ``hasConvergence`` 直接判假，
    避免渲染出一个空图表。
    """
    if not isinstance(raw_conv, dict):
        return None

    iterations = raw_conv.get("iterations") or []
    if not iterations:
        return None

    meta = raw_conv.get("metadata") or {}
    return {
        "iterations": iterations,
        "bestFitness": raw_conv.get("best_fitness") or raw_conv.get("bestFitness") or [],
        "avgFitness": raw_conv.get("avg_fitness") or raw_conv.get("avgFitness") or [],
        "diversity": raw_conv.get("diversity") or [],
        "medianFitness": raw_conv.get("median_fitness") or raw_conv.get("medianFitness") or [],
        "q1Fitness": raw_conv.get("q1_fitness") or raw_conv.get("q1Fitness") or [],
        "q3Fitness": raw_conv.get("q3_fitness") or raw_conv.get("q3Fitness") or [],
        "populationSnapshots": raw_conv.get("population_snapshots")
        or raw_conv.get("populationSnapshots"),
        "metadata": {
            "algorithm": meta.get("algorithm", "AOO"),
            "populationSize": meta.get("population_size", meta.get("populationSize", 0)),
            "eliteCount": meta.get("elite_count", meta.get("eliteCount", 0)),
            "convergenceRate": meta.get("convergence_rate", meta.get("convergenceRate", 0)),
            "convergenceIteration": meta.get(
                "convergence_iteration", meta.get("convergenceIteration", 0)
            ),
            "totalTimeSeconds": meta.get(
                "total_time_seconds", meta.get("totalTimeSeconds", 0)
            ),
        },
    }


def _path_to_response(record: LearningPath) -> Dict[str, Any]:
    """将 DB LearningPath 记录转为前端 LearningPath 接口格式
    path_data 实际结构 (由 OptimizationService._persist_results 写入):
      {
        "task_id": str,
        "diagnosis_id": str,
        "best_path": { "days": [...], "total_days": int, ... },
        "fitness_detail": dict,
        "alternative_paths": list,
        "convergence_data": dict,
        "pareto_front": list | None,
      }
    best_path.days[i] 结构:
      { "day": int, "tasks": [...], "total_minutes": int }
    """
    data = record.path_data or {}
    best_path = data.get("best_path", {}) or {}
    days = best_path.get("days", []) or []

    # 按天分组 dailyTasks 为前端 LearningTask[][] 嵌套格式
    daily_tasks = []
    for day_data in days:
        day_idx = day_data.get("day", 1)
        day_tasks = []
        for order, task in enumerate(day_data.get("tasks", [])):
            task_kp = task.get("knowledge_point", "")
            kp_name = task.get("kp_name", task.get("name", task_kp))
            day_tasks.append({
                "id": f"task-{day_idx}-{order}",
                "dayIndex": day_idx,
                "orderIndex": order + 1,
                "title": kp_name or task_kp,
                "description": f"学习 {kp_name or task_kp}",
                "knowledgePoint": task_kp,
                "estimatedMinutes": task.get("duration", 15),
                "difficulty": task.get("difficulty", 1),
                "resources": task.get("resources", []),
            })
        daily_tasks.append(day_tasks)

    # 计算 totalTasks
    total_tasks = sum(len(day_data.get("tasks", [])) for day_data in days)

    # 计算难度曲线
    difficulty_curve = []
    for day_data in days:
        tasks = day_data.get("tasks", [])
        if tasks:
            avg_diff = sum(t.get("difficulty", 1) for t in tasks) / len(tasks)
            difficulty_curve.append(round(avg_diff, 2))
        else:
            difficulty_curve.append(1.0)

    execution_time = data.get("convergence_data", {}) or {}
    if isinstance(execution_time, dict):
        execution_time = execution_time.get("execution_time", 0)
    else:
        execution_time = 0

    return {
        "id": str(record.id),
        "taskId": data.get("task_id") or str(record.id),
        "diagnosisId": data.get("diagnosis_id", ""),
        "userId": str(record.student_id),
        "createdAt": record.created_at.isoformat() if record.created_at else "",
        "totalDays": best_path.get("total_days", record.estimated_completion_days or 0),
        "totalTasks": total_tasks,
        "totalEstimatedHours": round(record.total_duration / 60.0, 1) if record.total_duration else 0,
        "difficultyCurve": difficulty_curve,
        "dailyTasks": daily_tasks,
        # 备选方案（速成冲刺 / 稳扎稳打 / 查漏补缺）与寻优回放数据
        # 必须一并返回，否则页面刷新后这两个功能会因缺数据而无法展示。
        "alternativePaths": _alternatives_to_response(
            data.get("alternative_paths") or []
        ),
        "convergenceData": _convergence_to_response(
            data.get("convergence_data") or {}
        ),
        "metadata": {
            "algorithm": "AOO",
            "optimizationScore": record.fitness_score or 0,
            "generationTime": execution_time,
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
    """获取当前学生生效（is_active=True）的学习路径。

    注意：必须按 is_active 过滤，而非仅取最新 created_at。
    否则待采纳的重规划版本（is_active=False 但 created_at 更新）会被误当作
    「当前路径」，导致用户点击「一键采纳」后刷新界面又回退到旧版本的现象。
    """
    # 1) 优先返回生效版本
    active_result = await db.execute(
        select(LearningPath)
        .where(
            LearningPath.student_id == current_user.id,
            LearningPath.is_active == True,  # noqa: E712
        )
        .order_by(desc(LearningPath.created_at))
        .limit(1)
    )
    record = active_result.scalar_one_or_none()

    # 2) 兜底：没有任何生效版本时，取最新创建的一条（避免空态）
    if record is None:
        fallback_result = await db.execute(
            select(LearningPath)
            .where(LearningPath.student_id == current_user.id)
            .order_by(desc(LearningPath.created_at))
            .limit(1)
        )
        record = fallback_result.scalar_one_or_none()

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
    """切换到备选路径方案

    支持两种 path_id:
      - 真实 UUID: 直接激活该条已存储路径
      - 逻辑 ID: efficiency / balanced / robust 或 alt-<type>
        从当前用户最新路径的 path_data.alternative_paths 中找到匹配方案，
        将其 best_path 提升为当前激活方案并持久化 (active_path_type)。
    """
    path_id = body.get("path_id", "")
    if not path_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="path_id 不能为空",
        )

    # 1) 真实 UUID: 直接激活
    #    注意：只有「解析 UUID 失败」才应回落到逻辑 ID 分支。
    #    若能解析成 UUID 却查不到记录，必须直接 404，不能被吞掉。
    try:
        uid = uuid.UUID(str(path_id))
    except (ValueError, AttributeError, TypeError):
        uid = None

    if uid is not None:
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
        return ResponseBase(
            message="已激活所选方案",
            data={"activePathId": str(record.id)},
        )

    # 2) 逻辑 ID: efficiency / balanced / robust / alt-<type>
    logic_type = str(path_id)
    if logic_type.startswith("alt-"):
        logic_type = logic_type[len("alt-"):]

    # 取该用户最新的一条路径
    res = await db.execute(
        select(LearningPath)
        .where(LearningPath.student_id == current_user.id)
        .order_by(LearningPath.created_at.desc())
        .limit(1)
    )
    record = res.scalar_one_or_none()
    if not record:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="尚未生成学习路径")

    path_data = record.path_data or {}
    alternatives = path_data.get("alternative_paths", []) or []

    # 备选方案由 OptimizationService._persist_results 写入，实际字段是
    # ``path_type``（并非 ``type``），且路径内容直接平铺为 ``days``，
    # 没有嵌套的 ``best_path``。这里对多种命名做兼容匹配。
    def _type_of(alt: Dict[str, Any]) -> str:
        return str(
            alt.get("path_type") or alt.get("pathType") or alt.get("type") or ""
        )

    matched = next(
        (
            a
            for a in alternatives
            if isinstance(a, dict) and _type_of(a) == logic_type
        ),
        None,
    )
    if not matched:
        available = [_type_of(a) for a in alternatives if isinstance(a, dict)]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"未找到类型为 {logic_type} 的备选方案"
                + (f"，可选：{', '.join(filter(None, available))}" if available else "")
            ),
        )

    # 取出该方案的路径内容：优先嵌套的 best_path，其次平铺的 days
    new_best_path = matched.get("best_path")
    if not new_best_path:
        days = matched.get("days") or []
        if days:
            new_best_path = {
                "days": days,
                "total_days": matched.get(
                    "total_days", matched.get("totalDays", len(days))
                ),
                "total_tasks": matched.get(
                    "total_tasks", matched.get("totalTasks", 0)
                ),
                "total_estimated_hours": matched.get(
                    "total_estimated_hours",
                    matched.get("totalEstimatedHours", 0),
                ),
                "fitness": matched.get("fitness", 0),
                "path_type": logic_type,
            }

    if not new_best_path:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="该备选方案缺少路径数据",
        )

    # 提升为当前激活方案并持久化
    path_data = dict(path_data)
    path_data["best_path"] = new_best_path
    path_data["active_path_type"] = logic_type
    record.path_data = path_data
    await db.commit()
    await db.refresh(record)

    return ResponseBase(
        message=f"已切换到「{matched.get('name', logic_type)}」方案",
        data={"activePathId": str(record.id), "activePathType": logic_type},
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
