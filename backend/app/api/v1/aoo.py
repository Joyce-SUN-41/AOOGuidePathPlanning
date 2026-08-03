"""AOO 路径优化 API — 触发优化 & 轮询状态

POST /api/v1/aoo/optimize        — 提交优化任务 (异步 Celery + 同步兜底)
GET  /api/v1/aoo/status/{task_id} — 轮询任务进度/结果 (建议 1-2 秒间隔)

状态流转:
  pending → processing → completed
                        → failed (含超时: >10分钟自动标记)
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.diagnosis import DiagnosisRecord
from app.models.learning_path import LearningPath
from app.models.user import User
from app.models.cognitive_profile import CognitiveProfileEvent
from app.schemas.aoo_optimize import (
    AOOOptimizeConfig,
    AOOOptimizeRequest,
    AOOOptimizeResponse,
    AOOOptimizeResult,
    AOOTaskStatusResponse,
    ConvergencePoint,
    OptimizeFlexibleRequest,
)
from app.services.diagnosis.adapter import DiagnosisAdapter
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
        "前端只需传入 diagnosis_id，后端从诊断数据库自动补全 student_id/mastery_levels/cognitive_load。"
        "请求返回 task_id，前端通过 GET /status/{task_id} 轮询进度。"
    ),
)
async def optimize_path(
    request: AOOOptimizeRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """触发 AOO 优化任务

    - 前端只需传入 diagnosis_id，其余字段从诊断数据库自动补全
    - Celery 优先；Celery 不可用时通过后台线程同步执行兜底
    """
    # ── 第一步: 从诊断数据库自动补全缺失字段 ──
    diagnosis_record = None
    need_db = (
        not request.student_id
        or not request.mastery_levels
        or request.cognitive_load is None
    )

    if need_db:
        try:
            diag_id = uuid.UUID(request.diagnosis_id)
            stmt = select(DiagnosisRecord).where(DiagnosisRecord.id == diag_id)
            result = await session.execute(stmt)
            diagnosis_record = result.scalar_one_or_none()
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的 diagnosis_id: {request.diagnosis_id}",
            )
        except Exception as exc:
            logger.warning("诊断记录查询失败: %s", exc)

        if diagnosis_record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"未找到诊断记录 diagnosis_id={request.diagnosis_id}，请先完成认知诊断",
            )

    # ── 自动补全 student_id ──
    if not request.student_id:
        request.student_id = str(diagnosis_record.student_id)

    # ── 权限校验: 学生只能操作自己的数据 ──
    if str(current_user.id) != str(request.student_id) and current_user.role != "teacher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能为自己的诊断数据创建优化任务",
        )

    # ── 自动补全 mastery_levels ──
    if not request.mastery_levels:
        raw_mastery = diagnosis_record.mastery_levels or {}
        extracted = {}
        for kp_id, data in raw_mastery.items():
            if isinstance(data, dict):
                extracted[kp_id] = float(data.get("mastery", 0.5))
            else:
                extracted[kp_id] = float(data)
        request.mastery_levels = extracted
        if not request.mastery_levels:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="诊断记录中无 mastery_levels 数据，请重新完成认知诊断",
            )

    # ── 自动补全 cognitive_load ──
    if request.cognitive_load is None:
        request.cognitive_load = (
            diagnosis_record.cognitive_load_index
            if diagnosis_record and diagnosis_record.cognitive_load_index is not None
            else 0.5
        )

    # ── 最终校验 ──
    if not request.student_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少 student_id")
    if not request.mastery_levels:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少 mastery_levels")
    if request.cognitive_load is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少 cognitive_load")

    logger.info(
        "AOO 优化请求: diagnosis=%s student=%s kps=%d load=%.2f",
        request.diagnosis_id, request.student_id,
        len(request.mastery_levels), request.cognitive_load,
    )

    # ── 第二步: 提取超参配置 ──
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

    # ── 第三步: 提交任务 (Celery 优先, 同步兜底) ──
    submitter_id = str(current_user.id)  # noqa: F841  # 预留, 供后续审计使用

    celery_available = False
    try:
        # 先检查 Celery Worker 是否在线 (ping 验证)
        inspect = run_aoo_optimization.app.control.inspect(timeout=2)
        workers = inspect.ping()
        celery_available = bool(workers)
    except Exception:
        celery_available = False

    # 尝试 Celery
    if celery_available:
        try:
            celery_task = run_aoo_optimization.delay(
                diagnosis_id=request.diagnosis_id,
                student_id=str(request.student_id),
                mastery_levels=request.mastery_levels,
                cognitive_load=request.cognitive_load,
                config=config_dict,
            )

            logger.info("Celery 任务已提交: task_id=%s", celery_task.id)
            return ResponseBase(
                message="优化任务已提交",
                data=AOOOptimizeResponse(
                    task_id=celery_task.id,
                    status="queued",
                    progress=0,
                    result=None,
                    error_message=None,
                ),
            )
        except Exception as celery_exc:
            logger.warning("Celery 不可用, 使用同步执行兜底: %s", celery_exc)
    else:
        logger.info("Celery Worker 离线, 直接使用同步执行")

    # ── 同步兜底 ──
    from app.tasks.aoo_optimization import run_aoo_optimization_sync

    try:
        sync_task_id = run_aoo_optimization_sync(
            diagnosis_id=request.diagnosis_id,
            student_id=str(request.student_id),
            mastery_levels=request.mastery_levels,
            cognitive_load=request.cognitive_load,
            config=config_dict,
        )

        logger.info("AOO 同步执行已启动: task_id=%s", sync_task_id)
        return ResponseBase(
            message="同步优化执行已启动",
            data=AOOOptimizeResponse(
                task_id=sync_task_id,
                status="queued",
                progress=0,
                result=None,
                error_message=None,
            ),
        )
    except Exception as sync_exc:
        logger.exception("同步执行启动失败")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AOO 优化服务暂时不可用: {str(sync_exc)}",
        )


# ============================================================
# POST /optimize-flexible — 灵活重规划 (诊断 / 诊断+对话)
# ============================================================


@router.post(
    "/optimize-flexible",
    response_model=ResponseBase[AOOOptimizeResponse],
    summary="灵活重规划 (基于任意历史诊断 / 诊断+对话)",
    description=(
        "支持两种重规划模式:\n"
        "- mode='diagnosis': 仅基于指定的一次「学习诊断」重新规划, 不混入对话信号\n"
        "- mode='diagnosis+chat': 基于指定诊断掌握度 + 当前「智能问答对话画像」融合后重规划\n"
        "  (融合逻辑: 诊断掌握度为基底, 对话画像按 λ 加权叠加, 复用 adapter.fuse_mastery)\n\n"
        "前端重规划选择器可列出历史诊断任选其一, 并勾选是否叠加对话分析。"
    ),
)
async def optimize_flexible(
    request: OptimizeFlexibleRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """灵活重规划入口

    - 与 /optimize 的区别: 允许任选历史诊断, 并支持叠加「对话画像」
    - 任务提交逻辑复用同一套 Celery/同步兜底
    """
    # 解析最终模式 (use_chat_profile 兼容覆盖)
    mode = request.mode
    if request.use_chat_profile is not None:
        mode = "diagnosis+chat" if request.use_chat_profile else "diagnosis"

    # ── 第一步: 读取指定诊断记录 (任意一次历史诊断) ──
    try:
        diag_id = uuid.UUID(request.diagnosis_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的 diagnosis_id: {request.diagnosis_id}",
        )

    stmt = select(DiagnosisRecord).where(DiagnosisRecord.id == diag_id)
    result = await session.execute(stmt)
    diagnosis_record = result.scalar_one_or_none()
    if diagnosis_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未找到诊断记录 diagnosis_id={request.diagnosis_id}",
        )

    # ── 自动补全 student_id ──
    student_id = request.student_id or str(diagnosis_record.student_id)
    if str(current_user.id) != student_id and current_user.role != "teacher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能为自己的诊断数据创建优化任务",
        )

    # ── 提取诊断掌握度 (基底) ──
    raw_mastery = diagnosis_record.mastery_levels or {}
    base_mastery: Dict[str, float] = {}
    for kp_id, data in raw_mastery.items():
        if isinstance(data, dict):
            base_mastery[kp_id] = float(data.get("mastery", 0.5))
        else:
            base_mastery[kp_id] = float(data)
    if not base_mastery:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该诊断记录中无 mastery_levels 数据，请重新完成认知诊断",
        )

    # ── 补全认知负荷 ──
    cognitive_load = request.cognitive_load
    if cognitive_load is None:
        cognitive_load = (
            diagnosis_record.cognitive_load_index
            if diagnosis_record.cognitive_load_index is not None
            else 0.5
        )

    # ── 第二步: 诊断+对话 模式 → 融合对话画像 ──
    final_mastery = base_mastery
    if mode == "diagnosis+chat":
        try:
            adapter = DiagnosisAdapter(
                db=session, user_id=uuid.UUID(student_id)
            )
            chat_profile = await adapter.get_chat_profile()
            chat_mastery: Dict[str, float] = {
                item["kp_id"]: item["level"]
                for item in chat_profile.get("items", [])
            }
            if chat_mastery:
                final_mastery = await adapter.fuse_mastery(
                    session=session,
                    student_id=uuid.UUID(student_id),
                    chat_mastery=chat_mastery,
                )
            else:
                logger.info(
                    "[optimize-flexible] 对话画像为空, 退化为单纯诊断重规划 (diag=%s)",
                    diag_id,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[optimize-flexible] 对话画像融合失败, 回退纯诊断: %s", exc)
            final_mastery = base_mastery

    # ── 提取超参配置 ──
    if request.config:
        config_dict = request.config.model_dump(exclude_none=True)
    else:
        config_dict = {
            "population_size": 50,
            "max_iterations": 500,
            "alpha": 0.6,
            "beta": 0.4,
        }

    logger.info(
        "AOO 灵活重规划: mode=%s diagnosis=%s student=%s kps=%d load=%.2f",
        mode, request.diagnosis_id, student_id, len(final_mastery), cognitive_load,
    )

    # ── 第三步: 提交任务 (Celery 优先, 同步兜底) ──
    celery_available = False
    try:
        inspect = run_aoo_optimization.app.control.inspect(timeout=2)
        workers = inspect.ping()
        celery_available = bool(workers)
    except Exception:
        celery_available = False

    if celery_available:
        try:
            celery_task = run_aoo_optimization.delay(
                diagnosis_id=request.diagnosis_id,
                student_id=student_id,
                mastery_levels=final_mastery,
                cognitive_load=cognitive_load,
                config=config_dict,
            )
            return ResponseBase(
                message="灵活优化任务已提交",
                data=AOOOptimizeResponse(
                    task_id=celery_task.id,
                    status="queued",
                    progress=0,
                    result=None,
                    error_message=None,
                ),
            )
        except Exception as celery_exc:
            logger.warning("Celery 不可用, 使用同步执行兜底: %s", celery_exc)
    else:
        logger.info("Celery Worker 离线, 直接使用同步执行")

    from app.tasks.aoo_optimization import run_aoo_optimization_sync

    try:
        sync_task_id = run_aoo_optimization_sync(
            diagnosis_id=request.diagnosis_id,
            student_id=student_id,
            mastery_levels=final_mastery,
            cognitive_load=cognitive_load,
            config=config_dict,
        )
        return ResponseBase(
            message="同步优化执行已启动",
            data=AOOOptimizeResponse(
                task_id=sync_task_id,
                status="queued",
                progress=0,
                result=None,
                error_message=None,
            ),
        )
    except Exception as sync_exc:
        logger.exception("同步执行启动失败")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AOO 优化服务暂时不可用: {str(sync_exc)}",
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
    try:
        return await _get_optimize_status_inner(task_id)
    except Exception as exc:
        logger.exception(
            "AOO 状态查询异常: task_id=%s error=%s", task_id, exc
        )
        return ResponseBase(
            data=AOOTaskStatusResponse(
                task_id=task_id,
                status="failed",
                progress=0,
                current_iteration=0,
                max_iterations=500,
                current_best_fitness=None,
                convergence_data=None,
                result=None,
                error=f"状态查询服务异常: {str(exc)[:200]}",
                created_at=None,
                updated_at=None,
            ),
        )


async def _get_optimize_status_inner(task_id: str):
    """状态查询核心逻辑"""
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

    # ── 5. 超时检测 ──

    # 5a. Pending 超时 (>15秒无进度, Celery Worker 可能未启动)
    if actual_status == "pending":
        pending_seconds = (
            (now - created_at).total_seconds()
            if created_at else 0
        )
        # 检查是否有 Celery 结果 (PENDING 状态可能表示 Celery Worker 未运行)
        try:
            celery_state = AsyncResult(task_id, app=run_aoo_optimization.app).state
            celery_never_started = celery_state and celery_state not in ("PENDING", "STARTED", "SUCCESS", "FAILURE")
        except Exception:
            celery_never_started = False

        if pending_seconds > 15 and not celery_never_started:
            logger.warning(
                "Celery 任务超时未启动 (pending >15s): task_id=%s, 建议前端使用同步兜底",
                task_id,
            )

    # 5b. Processing 超时 (>10分钟自动标记失败)
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

    # 6b. Skipped — 重复提交被去重锁拦截
    if actual_status == "skipped":
        max_iters = (
            progress_data.get("max_iterations", 500) if progress_data
            else (meta_data.get("config", {}).get("max_iterations", 500) if meta_data else 500)
        )
        return ResponseBase(
            data=AOOTaskStatusResponse(
                task_id=task_id,
                status="skipped",
                progress=0,
                current_iteration=0,
                max_iterations=max_iters,
                current_best_fitness=None,
                convergence_data=None,
                result=None,
                error="该学生已有进行中的优化任务, 请勿重复提交",
                created_at=created_at,
                updated_at=updated_at,
            ),
        )

    # 6c. Failed — 执行失败或超时
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
        conv_data = _build_convergence_point_safe(convergence_points)

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

        return ResponseBase(
            data=AOOTaskStatusResponse(
                task_id=task_id,
                status="processing",
                progress=min(round(raw_progress / 100.0, 3), 1.0),
                current_iteration=current_iter,
                max_iterations=max_iters,
                current_best_fitness=best_f,
                convergence_data=_build_convergence_point_safe(convergence_points),
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
            try:
                optimize_result = _parse_optimize_result(result_data["result"])
                conv_data = _build_convergence_point_from_complete(
                    result_data["result"].get("convergence_data")
                )
            except Exception as parse_exc:
                logger.warning(
                    "Redis 结果解析失败, 降级到收敛快照: task_id=%s error=%s",
                    task_id, parse_exc,
                )
                conv_data = _build_convergence_point_safe(convergence_points)
        else:
            # 降级: 从完整收敛快照构建
            conv_data = _build_convergence_point_safe(convergence_points)

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
    if redis_status == "skipped":
        # 重复提交被去重锁拦截: 视为终态, 前端提示"已有任务进行中"
        return "skipped"
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


def _build_convergence_point_safe(
    snapshots: list,
) -> Optional[ConvergencePoint]:
    """安全版 convergence 构建 — 过滤畸形数据，避免 KeyError 导致 500"""
    if not snapshots:
        return None

    valid_snapshots = [
        s for s in snapshots
        if isinstance(s, dict)
        and "iteration" in s
        and "best_fitness" in s
        and "avg_fitness" in s
    ]

    if not valid_snapshots:
        return None

    return _build_convergence_point(valid_snapshots)


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

    # 解析适应度详情 (Redis 中为数组, 取最佳路径对应的第一个)
    fd_raw_list = raw.get("fitness_detail", [])
    if isinstance(fd_raw_list, list) and len(fd_raw_list) > 0:
        fd_raw = fd_raw_list[0]
    elif isinstance(fd_raw_list, dict):
        fd_raw = fd_raw_list
    else:
        fd_raw = {}
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
        # 归一化 path_type: 空值或不合法值默认为 "balanced"
        raw_path_type = alt.get("path_type", "")
        if raw_path_type not in ("efficiency", "balanced", "robust"):
            raw_path_type = "balanced"
        alt_paths.append(AlternativePath(
            path_type=raw_path_type,
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


# ============================================================
# P2 重规划版本管理: 待采纳版本 / 一键采纳 / 版本差异
# ============================================================


def _extract_path_tasks(path: "LearningPath") -> list:
    """从 path_data.best_path 提取扁平化任务列表: [{kp_id, name, day, type, minutes}]"""
    tasks: list = []
    bp = (path.path_data or {}).get("best_path", {}) or {}
    for day_data in bp.get("days", []):
        day_idx = day_data.get("day", 1)
        for t in day_data.get("tasks", []):
            tasks.append({
                "kp_id": str(t.get("knowledge_point") or ""),
                "name": t.get("name", ""),
                "day": day_idx,
                "type": t.get("type", "reading"),
                "minutes": t.get("duration", 0),
            })
    return tasks


def _build_diff(old_path: "LearningPath", new_path: "LearningPath") -> dict:
    """计算两个路径版本的任务级差异"""
    old_tasks = {t["kp_id"]: t for t in _extract_path_tasks(old_path)}
    new_tasks = {t["kp_id"]: t for t in _extract_path_tasks(new_path)}

    added = [new_tasks[k] for k in new_tasks if k not in old_tasks]
    removed = [old_tasks[k] for k in old_tasks if k not in new_tasks]
    # 共有关键点: 对比所在天 / 类型变化
    changed = []
    for k in new_tasks:
        if k in old_tasks:
            o, n = old_tasks[k], new_tasks[k]
            diffs = {}
            if o["day"] != n["day"]:
                diffs["day"] = {"from": o["day"], "to": n["day"]}
            if o["type"] != n["type"]:
                diffs["type"] = {"from": o["type"], "to": n["type"]}
            if o["minutes"] != n["minutes"]:
                diffs["minutes"] = {"from": o["minutes"], "to": n["minutes"]}
            if diffs:
                changed.append({"kp_id": k, "name": n["name"], **diffs})

    return {
        "old_version": old_path.version if old_path else 0,
        "new_version": new_path.version,
        "old_path_id": str(old_path.id) if old_path else None,
        "new_path_id": str(new_path.id),
        "added": added,
        "removed": removed,
        "changed": changed,
        "summary": (
            f"新增 {len(added)} 个、移除 {len(removed)} 个、调整 {len(changed)} 个知识点任务"
        ),
    }


async def _fetch_path_explanation(
    path_id: uuid.UUID, student_id: uuid.UUID, session: AsyncSession
) -> Optional[str]:
    """P4: 读取该路径生成时写入的 path_regenerate 事件的 reasoning，作为可读解释。

    返回形如: 「基于对话中的掌握度变化，本次重规划生成第 N 版路径，适应度 X.XX；
    已为您保留为待采纳版本，可在「路径」页查看具体改动后决定是否应用。」
    """
    try:
        stmt = (
            select(CognitiveProfileEvent)
            .where(
                CognitiveProfileEvent.student_id == student_id,
                CognitiveProfileEvent.event_type == "path_regenerate",
                CognitiveProfileEvent.payload.op("->>")("path_id") == str(path_id),
            )
            .order_by(CognitiveProfileEvent.created_at.desc())
            .limit(1)
        )
        ev = (await session.execute(stmt)).scalar_one_or_none()
        if ev and ev.reasoning:
            return ev.reasoning
    except Exception as e:  # best-effort，绝不阻断主链路
        logger.warning("[_fetch_path_explanation] 读取解释失败: %s", e)
    return None


@router.get(
    "/pending-path",
    summary="查询待采纳的重规划版本",
    description="返回当前学生最新一条 is_active=False 的路径（对话触发生成的新版本），供前端展示 diff 与采纳。无则返回空。",
)
async def get_pending_path(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """查询待采纳版本（P2 重规划默认生成的版本，需用户一键采纳）"""
    stmt = (
        select(LearningPath)
        .where(
            LearningPath.student_id == current_user.id,
            LearningPath.is_active == False,  # noqa: E712
        )
        .order_by(LearningPath.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    pending = result.scalars().first()
    if pending is None:
        return ResponseBase(data=None, message="当前没有待采纳的重规划版本")

    # 计算与当前生效（父）版本的 diff
    diff = None
    if pending.parent_path_id is not None:
        parent = await session.get(LearningPath, pending.parent_path_id)
        if parent is not None:
            diff = _build_diff(parent, pending)

    # P4: 读取 path_regenerate 事件的 reasoning 作为「为什么路径变了」的可读解释
    explanation = await _fetch_path_explanation(pending.id, current_user.id, session)

    bp = (pending.path_data or {}).get("best_path", {}) or {}
    return ResponseBase(
        data={
            "path_id": str(pending.id),
            "version": pending.version,
            "parent_path_id": str(pending.parent_path_id) if pending.parent_path_id else None,
            "total_days": pending.estimated_completion_days,
            "total_minutes": pending.total_duration,
            "fitness_score": pending.fitness_score,
            "task_count": len(_extract_path_tasks(pending)),
            "created_at": pending.created_at.isoformat() if pending.created_at else None,
            "diff": diff,
            "explanation": explanation,
            "best_path_preview": {
                "total_days": bp.get("total_days"),
                "total_tasks": bp.get("total_tasks"),
            },
        },
        message="找到待采纳版本",
    )


@router.post(
    "/paths/{path_id}/adopt",
    summary="一键采纳重规划版本",
    description="将指定路径置为 is_active=True（生效），其原生效路径置 is_active=False。",
)
async def adopt_path(
    path_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """一键采纳指定重规划版本（P2）"""
    try:
        pid = uuid.UUID(path_id)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的 path_id: {path_id}",
        )

    target = await session.get(LearningPath, pid)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="路径不存在",
        )
    if str(target.student_id) != str(current_user.id) and current_user.role != "teacher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能采纳自己的学习路径",
        )
    if target.is_active:
        return ResponseBase(data={"path_id": path_id, "adopted": True}, message="该路径已生效")

    # 下线当前生效版本，上线目标版本
    old_active = await session.execute(
        select(LearningPath).where(
            LearningPath.student_id == current_user.id,
            LearningPath.is_active == True,  # noqa: E712
            LearningPath.id != pid,
        )
    )
    for old in old_active.scalars().all():
        old.is_active = False
        session.add(old)

    target.is_active = True
    session.add(target)
    await session.commit()

    logger.info(
        "[adopt] 学生 %s 采纳路径 v%d (path_id=%s)",
        current_user.id, target.version, pid,
    )
    return ResponseBase(
        data={"path_id": path_id, "adopted": True, "version": target.version},
        message=f"已采纳学习路径 v{target.version}",
    )


@router.get(
    "/paths/{path_id}/diff",
    summary="计算路径版本差异",
    description="返回指定路径相对其父版本（或指定 other_path_id）的任务级 diff，供前端高亮。",
)
async def get_path_diff(
    path_id: str,
    other_path_id: Optional[str] = Query(default=None, description="对比的目标版本 path_id，缺省为父版本"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """计算路径版本差异（P2 diff 高亮数据来源）"""
    try:
        pid = uuid.UUID(path_id)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的 path_id: {path_id}",
        )

    new_path = await session.get(LearningPath, pid)
    if new_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="路径不存在")

    old_path = None
    if other_path_id:
        try:
            oid = uuid.UUID(other_path_id)
            old_path = await session.get(LearningPath, oid)
        except (ValueError, AttributeError):
            pass
    elif new_path.parent_path_id is not None:
        old_path = await session.get(LearningPath, new_path.parent_path_id)

    if old_path is None:
        return ResponseBase(data=None, message="无对比基准版本（如首个版本）")

    if str(new_path.student_id) != str(current_user.id) and current_user.role != "teacher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权查看该路径差异",
        )

    return ResponseBase(data=_build_diff(old_path, new_path), message="版本差异计算完成")
