"""AOO 路径优化 API — 触发优化 & 轮询状态

POST /api/v1/aoo/optimize        — 提交优化任务 (异步 Celery 执行)
GET  /api/v1/aoo/status/{task_id} — 轮询任务进度/结果 (建议 1-2 秒间隔)

状态流转:
  pending → processing → completed
                        → failed (含超时: >10分钟自动标记)
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user
from app.models.learning_path import LearningPath
from app.models.user import User
from app.schemas.aoo_optimize import (
    AOOOptimizeConfig,
    AOOOptimizeRequest,
    AOOOptimizeResponse,
    AOOOptimizeResult,
    AOOTaskStatusResponse,
    ConvergencePoint,
)
from app.schemas.common import ResponseBase
from app.tasks.aoo_optimization import (
    get_task_convergence,
    get_task_error,
    get_task_meta,
    get_task_progress,
    get_task_result,
    get_task_status,
    is_task_timed_out,
    mark_task_failed,
    run_aoo_optimization,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/aoo", tags=["AOO Optimization"])


# ============================================================
# POST /optimize — 触发 AOO 路径优化
# ============================================================


@router.post(
    "/optimize",
    response_model=ResponseBase[AOOOptimizeResponse],
    summary="触发 AOO 路径优化",
    description=(
        "基于学生诊断数据和掌握度水平，运行 AOO 算法生成最优学习路径。"
        "请求返回 task_id，前端通过 GET /status/{task_id} 轮询进度。"
    ),
)
async def optimize_path(
    request: AOOOptimizeRequest,
    current_user: User = Depends(get_current_user),
):
    """触发 AOO 优化任务

    - 权限: 学生只能为自己的数据创建任务
    - 异步模式: Celery worker 后台执行，前端轮询 status 接口
    """
    # 权限校验: student_id 必须与当前登录用户一致 (学生角色)
    # 教师角色可跳过此校验（通过 student_id 指定查询目标）
    if str(current_user.id) != request.student_id and current_user.role != "teacher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能为自己的诊断数据创建优化任务",
        )

    # 提取超参配置
    config_dict = None
    if request.config:
        config_dict = request.config.model_dump(exclude_none=True)
    else:
        config_dict = {
            "population_size": 50,
            "max_iterations": 500,
            "alpha": 0.6,
            "beta": 0.4,
        }

    # 提交 Celery 异步任务
    try:
        celery_task = run_aoo_optimization.delay(
            diagnosis_id=request.diagnosis_id,
            student_id=request.student_id,
            mastery_levels=request.mastery_levels,
            cognitive_load=request.cognitive_load,
            config=config_dict,
        )
    except Exception as exc:
        logger.error("Celery 任务提交失败: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="任务队列不可用，请稍后重试 (Celery Worker 未启动)",
        )

    task_id = celery_task.id

    logger.info(
        "AOO 优化任务已入队: task_id=%s student=%s diagnosis=%s kps=%d",
        task_id, request.student_id, request.diagnosis_id,
        len(request.mastery_levels),
    )

    return ResponseBase(
        message="优化任务已提交",
        data=AOOOptimizeResponse(
            task_id=task_id,
            status="queued",
            progress=0,
            result=None,
            error_message=None,
        ),
    )


# ============================================================
# GET /status/{task_id} — 轮询任务状态
# ============================================================


@router.get(
    "/status/{task_id}",
    response_model=ResponseBase[AOOTaskStatusResponse],
    summary="查询 AOO 优化任务状态",
    description=(
        "前端以 1-2 秒间隔轮询此接口获取优化进度和结果。\n\n"
        "状态字段:\n"
        "- **pending**: 任务已入队, 等待 Worker 执行\n"
        "- **processing**: 正在执行优化, convergence_data 逐步累积\n"
        "- **completed**: 优化完成, result 中包含最佳路径和收敛曲线\n"
        "- **failed**: 执行失败或超时 (>10 分钟), error 中包含原因\n\n"
        "技术实现:\n"
        "1. 优先从 Redis 读取实时状态 (Celery broker)\n"
        "2. 完成时从数据库加载完整持久化结果作为兜底\n"
        "3. 超过 10 分钟无响应自动标记为 failed"
    ),
)
async def get_optimize_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """轮询任务状态

    建议前端以 1-2 秒间隔轮询, 支持绘制实时收敛曲线。
    """
    now = datetime.now(tz=timezone.utc)

    # ── 1. 从 Redis 读取状态 ──
    redis_status = get_task_status(task_id)
    progress_data = get_task_progress(task_id)
    meta_data = get_task_meta(task_id)
    error_data = get_task_error(task_id)

    # ── 2. 解析时间戳 ──
    created_at = _ts_to_datetime(meta_data.get("created_at") if meta_data else None)
    updated_at = _ts_to_datetime(
        meta_data.get("updated_at") if meta_data else None
    )

    # ── 3. 聚合收敛数据 ──
    convergence_points = get_task_convergence(task_id)

    # ── 4. 确定当前实际状态 ──
    actual_status = _resolve_status(
        task_id=task_id,
        redis_status=redis_status,
        progress_data=progress_data,
    )

    # ── 5. 超时检测 (>10分钟自动标记失败) ──
    if actual_status == "processing" and is_task_timed_out(task_id):
        logger.warning(
            "AOO 任务超时 (>10min): task_id=%s created_at=%s",
            task_id,
            created_at.isoformat() if created_at else "unknown",
        )
        mark_task_failed(
            task_id,
            f"优化任务超时 (超过 10 分钟无响应)，最后更新于 {updated_at}",
        )
        actual_status = "failed"
        error_data = {"error_message": "任务执行超时 (>10 分钟)", "updated_at": None}

    # ── 6. 根据状态返回响应 ──

    # 6a. Pending — 任务尚未开始
    if actual_status == "pending":
        max_iters = (meta_data.get("config", {}).get("max_iterations", 500)
                     if meta_data else 500)
        return ResponseBase(
            data=AOOTaskStatusResponse(
                task_id=task_id,
                status="pending",
                progress=0,
                current_iteration=0,
                max_iterations=max_iters,
                current_best_fitness=None,
                convergence_data=None,
                result=None,
                error=None,
                created_at=created_at,
                updated_at=updated_at,
            ),
        )

    # 6b. Failed — 执行失败或超时
    if actual_status == "failed":
        err_msg = "任务执行失败"
        if error_data:
            err_msg = error_data.get("error_message", err_msg)

        # 尝试从 Celery 获取更详细的错误信息
        try:
            celery_result = AsyncResult(task_id, app=run_aoo_optimization.app)
            if celery_result.failed() and str(celery_result.info):
                # 只在前 300 字符内取值，避免 Traceback 过长
                err_msg = str(celery_result.info)[:300]
        except Exception:
            pass

        max_iters = (
            progress_data.get("max_iterations", 500) if progress_data
            else (meta_data.get("config", {}).get("max_iterations", 500) if meta_data else 500)
        )
        current_iter = (
            progress_data.get("current_iteration", 0) if progress_data else 0
        )

        # 失败状态下也返回已累积的收敛数据，方便调试
        conv_data = _build_convergence_point(convergence_points) if convergence_points else None

        return ResponseBase(
            data=AOOTaskStatusResponse(
                task_id=task_id,
                status="failed",
                progress=round(
                    (progress_data.get("progress", 0) / 100.0) if progress_data else 0, 3
                ),
                current_iteration=current_iter,
                max_iterations=max_iters,
                current_best_fitness=(
                    progress_data.get("best_fitness_so_far")
                    if progress_data else None
                ),
                convergence_data=conv_data,
                result=None,
                error=err_msg,
                created_at=created_at,
                updated_at=updated_at,
            ),
        )

    # 6c. Processing — 正在执行中
    if actual_status == "processing":
        max_iters = (
            progress_data.get("max_iterations", 500) if progress_data
            else (meta_data.get("config", {}).get("max_iterations", 500) if meta_data else 500)
        )
        current_iter = (
            progress_data.get("current_iteration", 0) if progress_data else 0
        )
        best_f = (
            progress_data.get("best_fitness_so_far")
            if progress_data else None
        )
        raw_progress = progress_data.get("progress", 0) if progress_data else 0

        converged = convergence_points[-1].get("best_fitness") == 1.0 if convergence_points else False

        return ResponseBase(
            data=AOOTaskStatusResponse(
                task_id=task_id,
                status="processing",
                progress=min(round(raw_progress / 100.0, 3), 1.0),
                current_iteration=current_iter,
                max_iterations=max_iters,
                current_best_fitness=best_f,
                convergence_data=_build_convergence_point(convergence_points),
                result=None,
                error=None,
                created_at=created_at,
                updated_at=updated_at,
            ),
        )

    # 6d. Completed — 优化完成, 返回完整结果
    if actual_status == "completed":
        max_iters = (
            progress_data.get("max_iterations", 500) if progress_data
            else (meta_data.get("config", {}).get("max_iterations", 500) if meta_data else 500)
        )
        best_f = (
            progress_data.get("best_fitness_so_far")
            if progress_data else None
        )

        # 优先从 Redis 加载结果 (快速)
        optimize_result = None
        result_data = get_task_result(task_id)
        if result_data and result_data.get("result"):
            optimize_result = _parse_optimize_result(result_data["result"])
            conv_data = _build_convergence_point_from_complete(
                result_data["result"].get("convergence_data")
            )
        else:
            # 降级: 从完整收敛快照构建
            conv_data = _build_convergence_point(convergence_points)

        # 如果 Redis 中无结果, 从数据库加载 (兜底)
        if optimize_result is None:
            optimize_result = await _load_result_from_db(task_id)

        return ResponseBase(
            data=AOOTaskStatusResponse(
                task_id=task_id,
                status="completed",
                progress=1.0,
                current_iteration=max_iters,
                max_iterations=max_iters,
                current_best_fitness=best_f,
                convergence_data=conv_data,
                result=optimize_result,
                error=None,
                created_at=created_at,
                updated_at=updated_at,
            ),
        )

    # 兜底: 未知状态
    return ResponseBase(
        data=AOOTaskStatusResponse(
            task_id=task_id,
            status="pending",
            progress=0,
            current_iteration=0,
            max_iterations=500,
            current_best_fitness=None,
            convergence_data=None,
            result=None,
            error=None,
            created_at=created_at,
            updated_at=updated_at,
        ),
    )


# ============================================================
# 辅助函数
# ============================================================


def _resolve_status(
    task_id: str,
    redis_status: str,
    progress_data: Optional[dict],
) -> str:
    """综合 Redis 缓存 + Celery 状态, 解析为统一的状态枚举值"""
    # 1. 优先使用 Redis 中的明确状态
    if redis_status in ("completed", "failed"):
        return redis_status
    if redis_status in ("processing", "started"):
        return "processing"
    if redis_status == "queued":
        return "pending"

    # 2. Redis 无状态或 unknown → 回退到 Celery 查询
    if redis_status in ("unknown", "", None):
        try:
            celery_result = AsyncResult(task_id, app=run_aoo_optimization.app)
            celery_state = celery_result.state

            if celery_state == "PENDING":
                return "pending"
            elif celery_state in ("STARTED", "RETRY"):
                return "processing"
            elif celery_state == "SUCCESS":
                return "completed"
            elif celery_state in ("FAILURE", "REVOKED"):
                return "failed"
        except Exception:
            pass

    return "pending"


def _build_convergence_point(
    snapshots: list,
) -> Optional[ConvergencePoint]:
    """从 Redis 中累积的 ConvergenceSnapshot 列表构建 ConvergencePoint"""
    if not snapshots:
        return None

    return ConvergencePoint(
        iterations=[s["iteration"] for s in snapshots],
        best_fitness=[s["best_fitness"] for s in snapshots],
        avg_fitness=[s["avg_fitness"] for s in snapshots],
    )


def _build_convergence_point_from_complete(
    conv_data: Optional[dict],
) -> Optional[ConvergencePoint]:
    """从完成后完整的 convergence_data 字典构建 ConvergencePoint"""
    if not conv_data:
        return None

    return ConvergencePoint(
        iterations=conv_data.get("iterations", []),
        best_fitness=conv_data.get("best_fitness", []),
        avg_fitness=conv_data.get("avg_fitness", []),
    )


def _ts_to_datetime(ts: Optional[float]) -> Optional[datetime]:
    """Unix 时间戳 → ISO datetime (UTC)"""
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


async def _load_result_from_db(task_id: str) -> Optional[AOOOptimizeResult]:
    """从数据库 learning_paths 表加载完整结果 (Redis 数据过期时的兜底方案)

    通过 path_data JSONB 中的 task_id 字段精确匹配；
    若未匹配则降级返回最近一条有效结果。
    """
    from sqlalchemy import select, text
    from app.models.learning_path import LearningPath
    from app.services.aoo.optimization_service import _get_engine
    from sqlalchemy.ext.asyncio import AsyncSession

    try:
        engine = _get_engine()
        async with AsyncSession(engine) as session:
            # 尝试通过 task_id 精确匹配
            query = select(LearningPath).where(
                text("path_data ->> 'task_id' = :tid")
            ).params(tid=task_id).order_by(LearningPath.created_at.desc()).limit(1)

            result = await session.execute(query)
            lpath = result.scalars().first()

            if lpath and lpath.path_data and lpath.path_data.get("best_path"):
                return _result_from_learning_path(lpath)

            # 降级: 返回最近的有效结果
            fallback_query = (
                select(LearningPath)
                .where(text("path_data ? 'best_path'"))
                .order_by(LearningPath.created_at.desc())
                .limit(1)
            )
            fallback = await session.execute(fallback_query)
            lpath = fallback.scalars().first()

            if lpath:
                logger.info(
                    "DB 降级加载: task_id=%s 未精确匹配, 返回最近结果 path_id=%s",
                    task_id, lpath.id,
                )
                return _result_from_learning_path(lpath)

            logger.warning(
                "DB 兜底未找到 task_id=%s 的优化结果", task_id
            )

    except Exception as exc:
        logger.error("DB 兜底查询失败: %s", exc)

    return None


def _result_from_learning_path(lpath) -> AOOOptimizeResult:
    """从 LearningPath ORM 对象提取优化结果"""
    path_data = lpath.path_data or {}
    conv = path_data.get("convergence_data", {})
    bp = path_data.get("best_path", {})
    fd = path_data.get("fitness_detail", {})

    raw_result = {
        "best_path": bp,
        "fitness_detail": fd,
        "alternative_paths": path_data.get("alternative_paths", []),
        "convergence_data": conv,
        "pareto_front": path_data.get("pareto_front", {}),
        "execution_time": conv.get("metadata", {}).get(
            "total_time_seconds", 0
        ),
    }
    return _parse_optimize_result(raw_result)


def _parse_optimize_result(raw: dict) -> AOOOptimizeResult:
    """将原始结果字典转换为 Pydantic Schema"""
    from app.schemas.aoo import (
        AOOConvergenceData,
        BestPath,
        ConvergenceMetadata,
        PathDay,
        PathTaskInDay,
    )
    from app.schemas.aoo_optimize import (
        AlternativePath,
        PathFitnessDetail,
    )

    # 解析 BestPath
    bp_raw = raw.get("best_path", {})
    days = []
    for day_data in bp_raw.get("days", []):
        tasks = [
            PathTaskInDay(
                name=t.get("name", ""),
                duration=t.get("duration", 0),
                type=t.get("type", "reading"),
                knowledge_point=t.get("knowledge_point"),
                difficulty=t.get("difficulty"),
            )
            for t in day_data.get("tasks", [])
        ]
        days.append(PathDay(
            day=day_data.get("day", 1),
            tasks=tasks,
            total_minutes=day_data.get("total_minutes", 0),
            avg_difficulty=day_data.get("avg_difficulty", 0),
        ))

    best_path = BestPath(
        days=days,
        total_fitness=bp_raw.get("total_fitness", 0),
        total_days=bp_raw.get("total_days", 0),
        total_tasks=bp_raw.get("total_tasks", 0),
        total_estimated_hours=bp_raw.get("total_estimated_hours", 0),
    )

    # 解析适应度详情
    fd_raw = raw.get("fitness_detail", {})
    fitness_detail = PathFitnessDetail(
        total_fitness=fd_raw.get("total_fitness", 0),
        learning_effect=fd_raw.get("learning_effect", 0),
        coverage=fd_raw.get("coverage", 0),
        mastery_improvement=fd_raw.get("mastery_improvement", 0),
        avg_final_mastery=fd_raw.get("avg_final_mastery", 0),
        cognitive_load_score=fd_raw.get("cognitive_load_score", 0),
        daily_load_score=fd_raw.get("daily_load_score", 0),
        difficulty_density=fd_raw.get("difficulty_density", 0),
        prerequisite_violations=fd_raw.get("prerequisite_violations", 0),
        is_feasible=fd_raw.get("is_feasible", True),
        path_type=fd_raw.get("path_type", "optimal"),
    )

    # 解析备选路径
    alt_paths = []
    for alt in raw.get("alternative_paths", []):
        alt_days = []
        for day_data in alt.get("days", []):
            tasks = [
                PathTaskInDay(
                    name=t.get("name", ""),
                    duration=t.get("duration", 0),
                    type=t.get("type", "reading"),
                    knowledge_point=t.get("knowledge_point"),
                    difficulty=t.get("difficulty"),
                )
                for t in day_data.get("tasks", [])
            ]
            alt_days.append(PathDay(
                day=day_data.get("day", 1),
                tasks=tasks,
                total_minutes=day_data.get("total_minutes", 0),
                avg_difficulty=day_data.get("avg_difficulty", 0),
            ))
        alt_paths.append(AlternativePath(
            path_type=alt.get("path_type", "alternative"),
            days=alt_days,
            total_days=alt.get("total_days", 0),
            total_tasks=alt.get("total_tasks", 0),
            total_estimated_hours=alt.get("total_estimated_hours", 0),
            fitness=alt.get("fitness", 0),
        ))

    # 解析收敛数据
    conv_raw = raw.get("convergence_data", {})
    conv_meta_raw = conv_raw.get("metadata", {})
    convergence_data = AOOConvergenceData(
        iterations=conv_raw.get("iterations", []),
        best_fitness=conv_raw.get("best_fitness", []),
        avg_fitness=conv_raw.get("avg_fitness", []),
        diversity=conv_raw.get("diversity", []),
        median_fitness=conv_raw.get("median_fitness", []),
        q1_fitness=conv_raw.get("q1_fitness", []),
        q3_fitness=conv_raw.get("q3_fitness", []),
        population_snapshots=conv_raw.get("population_snapshots"),
        metadata=ConvergenceMetadata(
            algorithm=conv_meta_raw.get("algorithm", "AOO"),
            population_size=conv_meta_raw.get("population_size", 50),
            elite_count=conv_meta_raw.get("elite_count", 1),
            convergence_rate=conv_meta_raw.get("convergence_rate", 0),
            convergence_iteration=conv_meta_raw.get("convergence_iteration", 0),
            total_time_seconds=conv_meta_raw.get("total_time_seconds", 0),
        ),
    )

    return AOOOptimizeResult(
        best_path=best_path,
        fitness_detail=fitness_detail,
        alternative_paths=alt_paths,
        convergence_data=convergence_data,
        pareto_front=raw.get("pareto_front", {}),
        execution_time=raw.get("execution_time", 0),
    )
