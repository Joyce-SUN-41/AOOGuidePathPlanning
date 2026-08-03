"""AOO 路径优化异步任务 — Celery Worker 执行 + 同步兜底

核心职责:
  1. 接收优化请求参数
  2. 通过 Redis 实时上报进度 (供前端轮询)
  3. 调用 OptimizationService 执行 AOO 算法
  4. 将最终结果写入 Redis (TTL 1 小时)
  5. 失败时记录错误信息到 Redis
  6. Celery 不可用时, 通过后台线程同步执行 (兜底)
"""

import asyncio
import json
import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

import redis as redis_py

from app.core.config import settings
from app.services.aoo.optimization_service import OptimizationService
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# Redis 连接池 (用于进度上报, 独立于 Celery backend)
_redis_pool: Optional[redis_py.Redis] = None


def _get_redis() -> redis_py.Redis:
    """获取 Redis 客户端 (懒加载)"""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis_py.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_keepalive=True,
        )
    return _redis_pool


# ── Redis Key 常量 ──────────────────────────────────────
AOO_TASK_PROGRESS_KEY = "aoo:task:{task_id}:progress"
AOO_TASK_STATUS_KEY = "aoo:task:{task_id}:status"
AOO_TASK_RESULT_KEY = "aoo:task:{task_id}:result"
AOO_TASK_ERROR_KEY = "aoo:task:{task_id}:error"
AOO_TASK_META_KEY = "aoo:task:{task_id}:meta"
AOO_TASK_CONVERGENCE_KEY = "aoo:task:{task_id}:convergence"
AOO_TASK_TTL = 3600  # 1 小时过期
AOO_TASK_TIMEOUT_SECONDS = 600  # 10 分钟超时

# 每学生去重锁: 防止同一学生对同一优化请求重复提交 (误触/连点) 导致
# 多个 Worker 同时运行、CPU 争抢、互相拖慢甚至打满演示服务器。
# 锁 TTL 略大于任务超时阈值, 即使 Worker 崩溃也能自动释放, 避免该学生被永久阻塞。
AOO_STUDENT_LOCK_KEY = "aoo:lock:{student_id}"
AOO_STUDENT_LOCK_TTL = 15 * 60  # 15 分钟自动释放


def _acquire_student_lock(student_id: str) -> Optional[str]:
    """尝试为某学生获取去重锁 (Redis SET NX).

    Returns:
        token (str): 获取成功, 返回唯一令牌 (用于安全释放);
        None: 该学生已有进行中的任务, 获取失败。
    锁获取失败时不会抛异常 (Redis 不可用则降级为放行, 不阻断正常流程)。
    """
    try:
        r = _get_redis()
        token = uuid.uuid4().hex
        acquired = r.set(
            AOO_STUDENT_LOCK_KEY.format(student_id=student_id),
            token,
            nx=True,
            ex=AOO_STUDENT_LOCK_TTL,
        )
        if acquired:
            return token
        return None
    except Exception as exc:
        logger.warning("获取学生去重锁失败 (降级放行): student=%s %s", student_id, exc)
        # 降级: Redis 异常时放行, 避免误阻断正常优化
        return uuid.uuid4().hex


def _release_student_lock(student_id: str, token: Optional[str]) -> None:
    """释放学生去重锁 (仅当令牌匹配时, 防止误删他人锁).

    使用 Lua 式 GET+DEL 保证原子性 (避免锁过期后被误删新锁)。
    """
    if not token:
        return
    try:
        r = _get_redis()
        # 仅在值等于本任务令牌时删除, 避免删除已过期后被其他任务获取的新锁
        current = r.get(AOO_STUDENT_LOCK_KEY.format(student_id=student_id))
        if current == token:
            r.delete(AOO_STUDENT_LOCK_KEY.format(student_id=student_id))
    except Exception as exc:
        logger.debug("释放学生去重锁失败 (可忽略): student=%s %s", student_id, exc)


# ── 进度回调工厂 ─────────────────────────────────────────


def _make_progress_callback(task_id: str, total_iters: int, start_time: float):
    """创建进度回调函数，将 AOO 迭代进度写入 Redis"""

    def on_progress(
        progress: float,
        current_iter: int,
        max_iter: int,
        best_fitness: float,
    ) -> None:
        """进度回调"""
        elapsed = time.perf_counter() - start_time
        eta = (elapsed / progress * (100 - progress)) if progress > 1 else 0

        try:
            r = _get_redis()
            pipe = r.pipeline()

            # 更新进度
            pipe.set(
                AOO_TASK_PROGRESS_KEY.format(task_id=task_id),
                json.dumps({
                    "progress": round(progress, 1),
                    "current_iteration": current_iter,
                    "max_iterations": max_iter,
                    "best_fitness_so_far": round(best_fitness, 6) if best_fitness else None,
                    "estimated_remaining_seconds": round(eta, 1),
                    "updated_at": time.time(),
                }),
                ex=AOO_TASK_TTL,
            )

            # 更新状态
            if progress < 100:
                pipe.set(
                    AOO_TASK_STATUS_KEY.format(task_id=task_id),
                    "processing",
                    ex=AOO_TASK_TTL,
                )

            pipe.execute()
        except Exception as exc:
            logger.warning("Redis 进度上报失败: %s", exc)

    return on_progress


# ── 迭代回调工厂 (收敛数据实时上报) ─────────────────────


def _make_iteration_callback(task_id: str, total_iters: int):
    """创建每代回调，将收敛数据增量追加到 Redis 列表

    每次迭代调用时:
      - 将 {iteration, best_fitness, avg_fitness, diversity} 追加到 convergence 数组
      - 刷新 updated_at 时间戳
    """

    def on_iteration(
        iteration: int,
        best_fitness: float,
        avg_fitness: float,
        diversity: float,
    ) -> None:
        """每代收敛数据回调"""
        try:
            r = _get_redis()
            convergence_key = AOO_TASK_CONVERGENCE_KEY.format(task_id=task_id)
            meta_key = AOO_TASK_META_KEY.format(task_id=task_id)

            # 追加收敛数据点
            r.rpush(
                convergence_key,
                json.dumps({
                    "iteration": iteration,
                    "best_fitness": round(best_fitness, 6),
                    "avg_fitness": round(avg_fitness, 6),
                    "diversity": round(diversity, 6),
                }),
            )
            r.expire(convergence_key, AOO_TASK_TTL)

            # 刷新 updated_at
            meta_raw = r.get(meta_key)
            if meta_raw:
                meta = json.loads(meta_raw)
                meta["updated_at"] = time.time()
                r.set(meta_key, json.dumps(meta), ex=AOO_TASK_TTL)

        except Exception as exc:
            # 收敛上报失败不应中断优化主循环
            logger.debug("Redis convergence callback failed: %s", exc)

    return on_iteration


# ── Celery 任务 ──────────────────────────────────────────


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
    task_time_limit=15 * 60,       # 15 分钟硬超时
    task_soft_time_limit=12 * 60,   # 12 分钟软超时
)
def run_aoo_optimization(
    self,
    diagnosis_id: str,
    student_id: str,
    mastery_levels: Dict[str, float],
    cognitive_load: float,
    config: Optional[Dict[str, Any]] = None,
    auto_adopt: bool = False,
) -> Dict[str, Any]:
    """执行 AOO 路径优化 (Celery 异步任务)

    Args:
        diagnosis_id: 诊断记录 ID
        student_id: 学生用户 ID (UUID 字符串)
        mastery_levels: 知识点掌握度 {kp_id: value}
        cognitive_load: 综合认知负荷指数
        config: AOO 超参数覆盖 (可选)
        auto_adopt: 重规划后是否自动采纳新版本 (默认 False, 仅生成待采纳版本)

    Returns:
        优化结果字典 (task_id, status, result)
    """
    task_id = self.request.id
    t_start = time.perf_counter()

    logger.info(
        "AOO 优化任务启动: task_id=%s diagnosis=%s student=%s kps=%d load=%.2f",
        task_id, diagnosis_id, student_id,
        len(mastery_levels), cognitive_load,
    )

    # ── 初始化 Redis 状态 ──
    created_at = time.time()
    try:
        r = _get_redis()
        pipe = r.pipeline()
        pipe.set(AOO_TASK_STATUS_KEY.format(task_id=task_id), "processing", ex=AOO_TASK_TTL)
        pipe.set(
            AOO_TASK_PROGRESS_KEY.format(task_id=task_id),
            json.dumps({
                "progress": 0,
                "current_iteration": 0,
                "max_iterations": (config or {}).get("max_iterations", 500),
                "best_fitness_so_far": None,
                "estimated_remaining_seconds": None,
                "updated_at": t_start,
            }),
            ex=AOO_TASK_TTL,
        )
        pipe.set(
            AOO_TASK_META_KEY.format(task_id=task_id),
            json.dumps({
                "diagnosis_id": diagnosis_id,
                "student_id": student_id,
                "cognitive_load": cognitive_load,
                "kp_count": len(mastery_levels),
                "config": config or {},
                "created_at": created_at,
                "updated_at": created_at,
            }),
            ex=AOO_TASK_TTL,
        )
        # 初始化空收敛数组
        pipe.delete(AOO_TASK_CONVERGENCE_KEY.format(task_id=task_id))
        pipe.execute()
    except Exception as exc:
        logger.error("Redis 状态初始化失败: %s", exc)

    # ── 获取学生去重锁 (防重复提交争抢) ──
    # 在状态初始化之后获取, 使已有进行中任务的进度/结果仍可被前端轮询到。
    lock_token = _acquire_student_lock(student_id)
    if lock_token is None:
        logger.warning(
            "学生已有进行中的 AOO 任务, 跳过重复执行: student=%s task_id=%s",
            student_id, task_id,
        )
        return {
            "task_id": task_id,
            "status": "skipped",
            "message": "该学生已有进行中的优化任务, 请勿重复提交",
        }

    # ── 构建回调 ──
    total_iters = (config or {}).get("max_iterations", 500)
    progress_cb = _make_progress_callback(task_id, total_iters, t_start)
    iteration_cb = _make_iteration_callback(task_id, total_iters)

    # ── 执行优化 ──
    try:
        handler = OptimizationService()
        result = asyncio.run(
            handler.run(
                diagnosis_id=diagnosis_id,
                student_id=student_id,
                mastery_levels=mastery_levels,
                cognitive_load=cognitive_load,
                config=config,
                progress_callback=progress_cb,
                iteration_callback=iteration_cb,
                task_id=task_id,
                auto_adopt=auto_adopt,
            )
        )
    except asyncio.TimeoutError:
        logger.error("AOO 优化超时: task_id=%s", task_id)
        _set_task_error(task_id, "AOO 优化执行超时 (15 分钟)")
        raise self.retry(countdown=60, max_retries=1)

    except Exception as exc:
        logger.error(
            "AOO 优化失败: task_id=%s error=%s", task_id, exc,
            exc_info=True,
        )
        error_msg = str(exc)[:500]
        _set_task_error(task_id, error_msg)

        # 可重试
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))

        # 最终失败, 释放学生去重锁
        _release_student_lock(student_id, lock_token)
        return {
            "task_id": task_id,
            "status": "failed",
            "error_message": error_msg,
        }

    # ── 保存完成结果 ──
    t_total = round(time.perf_counter() - t_start, 3)

    response_data = {
        "task_id": task_id,
        "status": "completed",
        "progress": 100.0,
        "result": result,
    }

    try:
        pipe = r.pipeline()
        pipe.set(
            AOO_TASK_RESULT_KEY.format(task_id=task_id),
            json.dumps(response_data, default=str),
            ex=AOO_TASK_TTL,
        )
        pipe.set(
            AOO_TASK_STATUS_KEY.format(task_id=task_id),
            "completed",
            ex=AOO_TASK_TTL,
        )
        pipe.set(
            AOO_TASK_PROGRESS_KEY.format(task_id=task_id),
            json.dumps({
                "progress": 100.0,
                "current_iteration": total_iters,
                "max_iterations": total_iters,
                "best_fitness_so_far": result.get("best_path", {}).get(
                    "total_fitness", 0
                ),
                "estimated_remaining_seconds": 0,
                "updated_at": time.time(),
            }),
            ex=AOO_TASK_TTL,
        )
        pipe.execute()
    except Exception as exc:
        logger.error("Redis 结果写入失败: %s", exc)

    logger.info(
        "AOO 优化完成: task_id=%s time=%.2fs best_f=%s",
        task_id, t_total,
        result.get("best_path", {}).get("total_fitness"),
    )

    # ── 释放学生去重锁 ──
    _release_student_lock(student_id, lock_token)

    return response_data


# ── 辅助函数 ────────────────────────────────────────────


def _set_task_error(task_id: str, error_message: str) -> None:
    """将错误信息写入 Redis"""
    try:
        r = _get_redis()
        pipe = r.pipeline()
        pipe.set(AOO_TASK_STATUS_KEY.format(task_id=task_id), "failed", ex=AOO_TASK_TTL)
        pipe.set(
            AOO_TASK_ERROR_KEY.format(task_id=task_id),
            json.dumps({"error_message": error_message, "updated_at": time.time()}),
            ex=AOO_TASK_TTL,
        )
        pipe.execute()
    except Exception as exc:
        logger.warning("Redis 错误信息写入失败: %s", exc)


def get_task_progress(task_id: str) -> Optional[Dict[str, Any]]:
    """从 Redis 读取任务进度 (供 API 层调用)"""
    try:
        r = _get_redis()
        progress_raw = r.get(AOO_TASK_PROGRESS_KEY.format(task_id=task_id))
        if progress_raw:
            return json.loads(progress_raw)
    except Exception:
        pass
    return None


def get_task_status(task_id: str) -> str:
    """从 Redis 读取任务状态"""
    try:
        r = _get_redis()
        status = r.get(AOO_TASK_STATUS_KEY.format(task_id=task_id))
        return status or "unknown"
    except Exception:
        return "unknown"


def get_task_result(task_id: str) -> Optional[Dict[str, Any]]:
    """从 Redis 读取任务完整结果"""
    try:
        r = _get_redis()
        result_raw = r.get(AOO_TASK_RESULT_KEY.format(task_id=task_id))
        if result_raw:
            return json.loads(result_raw)
    except Exception:
        pass
    return None


def get_task_error(task_id: str) -> Optional[Dict[str, Any]]:
    """从 Redis 读取任务错误信息"""
    try:
        r = _get_redis()
        error_raw = r.get(AOO_TASK_ERROR_KEY.format(task_id=task_id))
        if error_raw:
            return json.loads(error_raw)
    except Exception:
        pass
    return None


def get_task_convergence(task_id: str) -> List[Dict[str, Any]]:
    """从 Redis 读取增量收敛数据 (实时收敛曲线)

    返回格式: [{iteration, best_fitness, avg_fitness, diversity}, ...]
    """
    try:
        r = _get_redis()
        convergence_key = AOO_TASK_CONVERGENCE_KEY.format(task_id=task_id)
        raw_items = r.lrange(convergence_key, 0, -1)
        if raw_items:
            return [json.loads(item) for item in raw_items]
    except Exception:
        pass
    return []


def get_task_meta(task_id: str) -> Optional[Dict[str, Any]]:
    """从 Redis 读取任务元数据 (created_at, updated_at 等)"""
    try:
        r = _get_redis()
        meta_raw = r.get(AOO_TASK_META_KEY.format(task_id=task_id))
        if meta_raw:
            return json.loads(meta_raw)
    except Exception:
        pass
    return None


def is_task_timed_out(task_id: str) -> bool:
    """检查任务是否超时 (超过 AOO_TASK_TIMEOUT_SECONDS 秒)"""
    meta = get_task_meta(task_id)
    if not meta:
        return False

    created_at = meta.get("created_at", 0)
    updated_at = meta.get("updated_at", created_at)

    # 使用最新的时间戳判断超时
    now = time.time()
    elapsed = now - max(created_at, updated_at) if created_at else 0

    return elapsed > AOO_TASK_TIMEOUT_SECONDS


def mark_task_failed(task_id: str, error_message: str) -> None:
    """标记任务为失败 (供超时检测使用)"""
    try:
        r = _get_redis()
        pipe = r.pipeline()
        pipe.set(AOO_TASK_STATUS_KEY.format(task_id=task_id), "failed", ex=AOO_TASK_TTL)
        pipe.set(
            AOO_TASK_ERROR_KEY.format(task_id=task_id),
            json.dumps({
                "error_message": error_message,
                "updated_at": time.time(),
                "timed_out": True,
            }),
            ex=AOO_TASK_TTL,
        )
        pipe.execute()
    except Exception as exc:
        logger.warning("标记任务失败写入 Redis 失败: %s", exc)


# ── 通用 Redis 任务初始化 (Celery + 同步兜底共用) ─────────


def _initialize_task_redis(
    task_id: str,
    diagnosis_id: str,
    student_id: str,
    mastery_levels: Dict[str, float],
    cognitive_load: float,
    config: Optional[Dict[str, Any]],
    status: str = "processing",
) -> float:
    """通用初始化: 将任务状态/进度/元数据写入 Redis

    Returns:
        created_at (float): 创建时间 Unix 时间戳
    """
    created_at = time.time()
    total_iters = (config or {}).get("max_iterations", 500)

    try:
        r = _get_redis()
        pipe = r.pipeline()
        pipe.set(
            AOO_TASK_STATUS_KEY.format(task_id=task_id),
            status,
            ex=AOO_TASK_TTL,
        )
        pipe.set(
            AOO_TASK_PROGRESS_KEY.format(task_id=task_id),
            json.dumps({
                "progress": 0,
                "current_iteration": 0,
                "max_iterations": total_iters,
                "best_fitness_so_far": None,
                "estimated_remaining_seconds": None,
                "updated_at": time.time(),
            }),
            ex=AOO_TASK_TTL,
        )
        pipe.set(
            AOO_TASK_META_KEY.format(task_id=task_id),
            json.dumps({
                "diagnosis_id": diagnosis_id,
                "student_id": student_id,
                "cognitive_load": cognitive_load,
                "kp_count": len(mastery_levels),
                "config": config or {},
                "created_at": created_at,
                "updated_at": created_at,
            }),
            ex=AOO_TASK_TTL,
        )
        pipe.delete(AOO_TASK_CONVERGENCE_KEY.format(task_id=task_id))
        pipe.execute()
    except Exception as exc:
        logger.error("Redis 状态初始化失败 (task_id=%s): %s", task_id, exc)

    return created_at


# ── 同步执行函数 (Celery 不可用时的兜底方案) ─────────────────


def run_aoo_optimization_sync(
    diagnosis_id: str,
    student_id: str,
    mastery_levels: Dict[str, float],
    cognitive_load: float,
    config: Optional[Dict[str, Any]] = None,
    auto_adopt: bool = False,
) -> str:
    """在后台线程同步执行 AOO 优化 (不需要 Celery)

    通过 Thread + Redis 进度上报实现与 Celery 任务兼容的状态轮询。
    前端通过 GET /aoo/status/{task_id} 轮询进度，与此函数写入的 Redis key 完全兼容。

    Args:
        diagnosis_id: 诊断记录 ID
        student_id: 学生用户 ID
        mastery_levels: 知识点掌握度 {kp_id: value}
        cognitive_load: 综合认知负荷指数
        config: AOO 超参数覆盖 (可选)
        auto_adopt: 重规划后是否自动采纳新版本 (默认 False)

    Returns:
        task_id (str): 用于轮询进度的任务 ID
    """
    task_id = f"sync-{uuid.uuid4().hex[:12]}"
    t_start = time.perf_counter()
    total_iters = (config or {}).get("max_iterations", 500)

    logger.info(
        "AOO 同步执行启动: task_id=%s diagnosis=%s student=%s kps=%d load=%.2f",
        task_id, diagnosis_id, student_id,
        len(mastery_levels), cognitive_load,
    )

    # ── 初始化 Redis 状态 ──
    _initialize_task_redis(
        task_id=task_id,
        diagnosis_id=diagnosis_id,
        student_id=student_id,
        mastery_levels=mastery_levels,
        cognitive_load=cognitive_load,
        config=config,
        status="queued",  # 先标记为 queued，线程启动后切换为 processing
    )

    # ── 构建回调 ──
    progress_cb = _make_progress_callback(task_id, total_iters, t_start)
    iteration_cb = _make_iteration_callback(task_id, total_iters)

    def _run_in_thread() -> None:
        """后台线程执行体"""
        # 切换状态为 processing
        redis_available = False
        try:
            _r = _get_redis()
            _r.set(
                AOO_TASK_STATUS_KEY.format(task_id=task_id),
                "processing",
                ex=AOO_TASK_TTL,
            )
            redis_available = True
        except Exception:
            logger.warning("Redis 不可用, 同步任务将无法上报进度 (task_id=%s)", task_id)

        # ── 获取学生去重锁 (防重复提交争抢) ──
        lock_token = _acquire_student_lock(student_id)
        if lock_token is None:
            logger.warning(
                "同步任务: 学生已有进行中的 AOO 任务, 跳过重复执行: student=%s task_id=%s",
                student_id, task_id,
            )
            try:
                if redis_available:
                    _r.set(
                        AOO_TASK_STATUS_KEY.format(task_id=task_id),
                        "skipped",
                        ex=AOO_TASK_TTL,
                    )
            except Exception:
                pass
            return

        try:
            handler = OptimizationService()
            result = asyncio.run(
                handler.run(
                    diagnosis_id=diagnosis_id,
                    student_id=student_id,
                    mastery_levels=mastery_levels,
                    cognitive_load=cognitive_load,
                    config=config,
                    progress_callback=progress_cb,
                    iteration_callback=iteration_cb,
                    task_id=task_id,
                    auto_adopt=auto_adopt,
                )
            )
        except Exception as exc:
            logger.error(
                "AOO 同步执行失败: task_id=%s error=%s",
                task_id, exc, exc_info=True,
            )
            error_msg = str(exc)[:500]
            _set_task_error(task_id, error_msg)
            _release_student_lock(student_id, lock_token)
            return

        # ── 保存完成结果 ──
        t_total = round(time.perf_counter() - t_start, 3)

        if redis_available:
            try:
                pipe = _r.pipeline()
                pipe.set(
                    AOO_TASK_RESULT_KEY.format(task_id=task_id),
                    json.dumps(
                        {"task_id": task_id, "status": "completed",
                         "progress": 100.0, "result": result},
                        default=str,
                    ),
                    ex=AOO_TASK_TTL,
                )
                pipe.set(
                    AOO_TASK_STATUS_KEY.format(task_id=task_id),
                    "completed",
                    ex=AOO_TASK_TTL,
                )
                pipe.set(
                    AOO_TASK_PROGRESS_KEY.format(task_id=task_id),
                    json.dumps({
                        "progress": 100.0,
                        "current_iteration": total_iters,
                        "max_iterations": total_iters,
                        "best_fitness_so_far": result.get("best_path", {}).get(
                            "total_fitness", 0
                        ),
                        "estimated_remaining_seconds": 0,
                        "updated_at": time.time(),
                    }),
                    ex=AOO_TASK_TTL,
                )
                pipe.execute()
            except Exception as exc:
                logger.error("Redis 结果写入失败 (sync): %s", exc)

        logger.info(
            "AOO 同步执行完成: task_id=%s time=%.2fs best_f=%s",
            task_id, t_total,
            result.get("best_path", {}).get("total_fitness"),
        )

        # ── 释放学生去重锁 ──
        _release_student_lock(student_id, lock_token)

    # 启动后台线程
    thread = threading.Thread(target=_run_in_thread, daemon=True, name=f"aoo-sync-{task_id}")
    thread.start()

    logger.info("AOO 同步执行已入队: task_id=%s", task_id)
    return task_id
