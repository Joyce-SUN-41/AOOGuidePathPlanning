"""AOO 路径优化服务层 — 数据加载 / 算法调用 / 结果持久化

负责:
  1. 从数据库加载知识点 & 测绘数据
  2. 将持久化数据转换为 AOO 算法所需格式
  3. 调用 AOOService.optimize()
  4. 将结果保存到 learning_paths / path_tasks / aoo_optimization_logs

使用方式 (Celery task):
    handler = OptimizationService()
    result = await handler.run(diagnosis_id="...", student_id="...",
                               mastery_levels={...}, cognitive_load=0.35,
                               config={...}, progress_callback=...)
"""

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import UUID

import numpy as np
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.aoo_optimization_log import AOOOptimizationLog
from app.models.cognitive_profile import CognitiveProfileEvent
from app.models.learning_path import LearningPath
from app.models.knowledge_graph import KnowledgeGraphEdge
from app.models.knowledge_point import KnowledgePoint
from app.models.path_task import PathTask
from app.models.student_knowledge import StudentKnowledge
from app.services.aoo import aoo_service
from app.services.aoo.aoo_config import AOOConfig
from app.services.aoo.fitness_calculator import KnowledgePointMeta

logger = logging.getLogger(__name__)

# Celery worker 中使用独立的异步引擎
_engine = None


def _get_engine():
    """获取或创建异步数据库引擎 (单例, 供 Celery worker 使用)"""
    global _engine
    if _engine is None:
        db_url = settings.effective_database_url
        _engine = create_async_engine(
            db_url,
            echo=False,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
    return _engine


class OptimizationService:
    """AOO 优化工作流处理器"""

    def __init__(self) -> None:
        self._creation_order: List[int] = []

    # ============================================================
    # 主入口: 完整优化工作流
    # ============================================================

    async def run(
        self,
        *,
        diagnosis_id: str,
        student_id: str,
        mastery_levels: Dict[str, float],
        cognitive_load: float,
        config: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[callable] = None,
        iteration_callback: Optional[callable] = None,
        task_id: Optional[str] = None,
        auto_adopt: bool = False,
    ) -> Dict[str, Any]:
        """执行完整 AOO 优化工作流

        Args:
            diagnosis_id: 测绘记录 ID
            student_id: 学生用户 ID
            mastery_levels: 知识点掌握度映射 {kp_id: value ∈ [0,1]}
            cognitive_load: 综合认知负荷指数
            config: 可选的 AOO 超参数覆盖
            progress_callback: 进度回调 callable(progress_pct, current_iter, max_iter, best_f)
            iteration_callback: 每代回调 callable(iter, best_f, avg_f, diversity)，用于实时收敛上报
            task_id: Celery 任务 ID (用于 DB 关联)
            auto_adopt: 重规划后是否自动采纳新版本（默认 False，仅生成待采纳版本）

        Returns:
            AOO 优化结果字典
        """
        t0 = time.perf_counter()

        # 1. 加载知识点元数据
        kp_metas = await self._load_knowledge_point_metas()

        if not kp_metas:
            logger.warning("数据库中无知识点记录，AOO 优化无数据可执行")
            return self._empty_result(diagnosis_id)

        # 2. 构建 AOO 配置
        aoo_config = self._build_config(config, dim=len(kp_metas))

        # 3. 获取已有掌握度 (合并 mastery_levels)
        #    valid_kp_ids 作为白名单，拦截任何非法/非 UUID 键流入下游
        valid_kp_ids = {str(k.id) for k in kp_metas}
        full_mastery = await self._merge_student_mastery(
            student_id, mastery_levels, valid_kp_ids=valid_kp_ids
        )

        # 4. 转换知识点数据为 FitnessCalculator 所需格式
        kp_meta_dicts = [self._kp_to_meta(k) for k in kp_metas]

        # 5. 构建侧写
        preferences = {
            "population_size": aoo_config.population_size,
            "max_iterations": aoo_config.max_iterations,
            "alpha": aoo_config.alpha,
            "beta": aoo_config.beta,
        }
        if config and config.get("max_days"):
            preferences["max_days"] = config["max_days"]
        if config and config.get("max_daily_minutes"):
            preferences["max_daily_minutes"] = config["max_daily_minutes"]
        # 第三维「学习准备度」（建议 3）与学习风格（建议 4）作为独立自变量透传
        # 仅当 config 提供且非空时注入；为空则二维/单维模式，不影响优化流程
        if config:
            readiness = config.get("readiness")
            if isinstance(readiness, dict) and any(
                k in readiness for k in ("motivation", "metacognition", "self_efficacy")
            ):
                preferences["readiness"] = {
                    "motivation": float(readiness.get("motivation", 0.0)),
                    "metacognition": float(readiness.get("metacognition", 0.0)),
                    "self_efficacy": float(readiness.get("self_efficacy", 0.0)),
                }
            learning_style = config.get("learning_style")
            if isinstance(learning_style, dict) and learning_style.get("label") not in (None, "未评估"):
                preferences["learning_style"] = {
                    "label": str(learning_style.get("label")),
                    "scores": learning_style.get("scores", {}) or {},
                }
            elif isinstance(learning_style, str) and learning_style != "未评估":
                preferences["learning_style"] = {"label": learning_style, "scores": {}}

        # 6. 确定薄弱知识点
        #    P0 修复: 必须是 AOO 认识的真实 kp_id，否则 focus_areas 会被污染
        #    (历史上中文 kp_name 曾混入此处，导致优化目标失效)
        focus_areas = [
            kp_id for kp_id, v in full_mastery.items()
            if v < 0.6 and kp_id in valid_kp_ids
        ]

        # 7. 上报进度
        if progress_callback:
            await self._safe_callback(
                progress_callback, 5, 0, aoo_config.max_iterations, 0
            )

        # 8. 调用 AOO 引擎
        start_exec = time.perf_counter()
        result = await aoo_service.optimize(
            diagnosis_id=diagnosis_id,
            knowledge_points=kp_meta_dicts,
            student_mastery=full_mastery,
            focus_areas=focus_areas,
            preferences=preferences,
            config=aoo_config,
            iteration_callback=iteration_callback,
        )
        execution_time = round(time.perf_counter() - start_exec, 3)

        if progress_callback:
            await self._safe_callback(
                progress_callback, 95, aoo_config.max_iterations,
                aoo_config.max_iterations,
                result.get("best_path_fitness", {}).get("total_fitness", 0),
            )

        # 9. 构建 API 兼容结果
        optimize_result = self._build_optimize_result(
            result, execution_time
        )

        # 10. 持久化结果
        student_uuid = UUID(student_id)
        try:
            await self._persist_results(
                student_id=student_uuid,
                diagnosis_id=diagnosis_id,
                result=result,
                optimize_result=optimize_result,
                aoo_config=aoo_config,
                task_id=task_id,
                auto_adopt=auto_adopt,
                focus_areas=focus_areas,
            )
        except Exception as exc:
            logger.error(
                "持久化 AOO 结果失败 (非致命): %s", exc, exc_info=True
            )

        if progress_callback:
            await self._safe_callback(progress_callback, 100,
                                       aoo_config.max_iterations,
                                       aoo_config.max_iterations,
                                       optimize_result.get("best_path", {}).get("total_fitness", 0))

        logger.info(
            "AOO 优化完成: cehui=%s total=%.2fs best_f=%.6f",
            diagnosis_id, execution_time,
            optimize_result.get("best_path", {}).get("total_fitness", 0),
        )

        return optimize_result

    # ============================================================
    # 数据加载
    # ============================================================

    async def _load_knowledge_point_metas(self) -> List[KnowledgePoint]:
        """从数据库加载所有知识点的 ORM 对象（含前置依赖关系）"""
        engine = _get_engine()
        async with AsyncSession(engine) as session:
            result = await session.execute(
                select(KnowledgePoint)
                .options(
                    selectinload(KnowledgePoint.children),
                    selectinload(KnowledgePoint.incoming_edges),
                )
                .order_by(KnowledgePoint.created_at)
            )
            return list(result.scalars().all())

    async def _merge_student_mastery(
        self,
        student_id: str,
        incoming: Dict[str, float],
        valid_kp_ids: Optional[set] = None,
    ) -> Dict[str, float]:
        """显式三源合并学生掌握度，键空间统一为 kp_id (UUID 字符串)

        优先级 (高 → 低):
          1. incoming   — 本次请求携带的掌握度 (测绘结果 / 已融合的问答修正)
          2. StudentKnowledge — 客观答题记录沉淀
          3. 缺省       — 不填充，交由 FitnessCalculator 使用其默认值

        P0 修复说明:
          旧实现用 `if kp_id not in merged` 做"先到先得填空"，语义模糊；
          且不校验键合法性，导致非 UUID 键（如 LLM 输出的中文名）
          可以一路流到 focus_areas 污染优化目标。
          现改为显式覆盖语义 + 白名单过滤。

        Args:
            valid_kp_ids: 合法 kp_id 白名单。非 None 时，不在白名单内的键
                          将被丢弃并记录日志（不静默吞掉，保证可观测）。
        """
        merged: Dict[str, float] = {}
        dropped: List[str] = []

        def _accept(kp_id: str, value: float) -> bool:
            if valid_kp_ids is not None and kp_id not in valid_kp_ids:
                dropped.append(kp_id)
                return False
            merged[kp_id] = max(0.0, min(1.0, float(value)))
            return True

        # 源 2: 答题记录 (先写入，允许被高优先级源覆盖)
        try:
            engine = _get_engine()
            async with AsyncSession(engine) as session:
                result = await session.execute(
                    select(StudentKnowledge).where(
                        StudentKnowledge.student_id == UUID(student_id)
                    )
                )
                for r in result.scalars().all():
                    try:
                        _accept(str(r.kp_id), float(r.mastery_level))
                    except (TypeError, ValueError):
                        continue
        except Exception as exc:
            logger.warning("加载历史掌握度失败: %s", exc)

        # 源 1: 请求携带 (最高优先级，显式覆盖答题记录)
        for kp_id, value in (incoming or {}).items():
            try:
                _accept(str(kp_id), float(value))
            except (TypeError, ValueError):
                continue

        if dropped:
            logger.warning(
                "[aoo] 已丢弃 %d 个非法/未知知识点键 (前 5 个: %s)，"
                "疑似上游未做 kp_name→kp_id 对齐",
                len(dropped), dropped[:5],
            )

        return merged

    # ============================================================
    # 数据转换
    # ============================================================

    @staticmethod
    def _kp_to_meta(kp: KnowledgePoint) -> Dict[str, Any]:
        """将 ORM 对象转换为 FitnessCalculator 所需的 dict 格式"""
        # 从 incoming_edges 关系获取前置知识点ID列表
        prereq_ids = [
            str(edge.source_kp_id) for edge in (kp.incoming_edges or [])
        ]
        return {
            "id": str(kp.id),
            "name": kp.name,
            "difficulty": float(kp.difficulty_level),
            "layer": kp.layer or "core",
            "prerequisites": prereq_ids,
            "estimated_hours": 1.0,  # 数据库中暂无此字段, 默认 1 小时
            "subject": kp.subject,
        }

    # ============================================================
    # 配置构建
    # ============================================================

    @staticmethod
    def _build_config(
        config: Optional[Dict[str, Any]],
        dim: int,
    ) -> AOOConfig:
        """从用户配置构建 AOOConfig"""
        cfg = AOOConfig(dim=dim)

        if config:
            for key, value in config.items():
                if hasattr(cfg, key) and value is not None:
                    setattr(cfg, key, value)

        # 确保认知负荷设置合理
        if cfg.beta <= 0:
            cfg.beta = 0.4

        return cfg

    # ============================================================
    # 结果构建
    # ============================================================

    def _build_optimize_result(
        self,
        raw: Dict[str, Any],
        execution_time: float,
    ) -> Dict[str, Any]:
        """将 AOOService 返回的原始结果转换为 API 契约格式"""
        best_path = raw.get("best_path", {})
        best_fitness = raw.get("best_path_fitness", {})
        alternatives = raw.get("alternative_paths", [])
        convergence = raw.get("convergence", {})
        pareto = raw.get("pareto_front", {})

        # 构建 BestPath
        best_path_obj = {
            "days": best_path.get("days", []),
            "total_days": best_path.get("total_days", 0),
            "total_tasks": best_path.get("total_tasks", 0),
            "total_estimated_hours": best_path.get("total_estimated_hours", 0),
            "total_fitness": best_fitness.get("total_fitness", 0),
        }

        # 构建适应度详情
        fitness_detail = {
            "total_fitness": best_fitness.get("total_fitness", 0),
            "learning_effect": best_fitness.get("learning_effect", 0),
            "coverage": best_fitness.get("coverage", 0),
            "mastery_improvement": best_fitness.get("mastery_improvement", 0),
            "avg_final_mastery": best_fitness.get("avg_final_mastery", 0),
            "cognitive_load_score": best_fitness.get("cognitive_load_score", 0),
            "daily_load_score": best_fitness.get("daily_load_score", 0),
            "difficulty_density": best_fitness.get("difficulty_density", 0),
            "prerequisite_violations": best_fitness.get("prerequisite_violations", 0),
            "is_feasible": best_fitness.get("is_feasible", True),
            "path_type": best_fitness.get("path_type", "optimal"),
        }

        # 构建备选路径
        alt_paths = []
        for alt in alternatives:
            fr = alt.get("fitness_result", {})
            alt_paths.append({
                "path_type": alt.get("path_type", "alternative"),
                "days": alt.get("days", []),
                "total_days": alt.get("total_days", 0),
                "total_tasks": alt.get("total_tasks", 0),
                "total_estimated_hours": alt.get("total_estimated_hours", 0),
                "fitness": fr.get("total_fitness", 0),
            })

        # 构建收敛数据
        conv_meta = convergence.get("metadata", {})
        convergence_data = {
            "iterations": convergence.get("iterations", []),
            "best_fitness": convergence.get("best_fitness", []),
            "avg_fitness": convergence.get("avg_fitness", []),
            "diversity": convergence.get("diversity", []),
            "median_fitness": convergence.get("median_fitness", []),
            "q1_fitness": convergence.get("q1_fitness", []),
            "q3_fitness": convergence.get("q3_fitness", []),
            "population_snapshots": convergence.get("population_snapshots"),
            "metadata": {
                "algorithm": conv_meta.get("algorithm", "AOO"),
                "population_size": conv_meta.get("population_size", 50),
                "elite_count": conv_meta.get("elite_count", 1),
                "convergence_rate": conv_meta.get("convergence_rate", 0),
                "convergence_iteration": conv_meta.get("convergence_iteration", 0),
                "total_time_seconds": execution_time,
            },
        }

        return {
            "best_path": best_path_obj,
            "fitness_detail": fitness_detail,
            "alternative_paths": alt_paths,
            "convergence_data": convergence_data,
            "pareto_front": pareto,
            "execution_time": execution_time,
        }

    # ============================================================
    # 结果持久化
    # ============================================================

    async def _persist_results(
        self,
        student_id: UUID,
        diagnosis_id: str,
        result: Dict[str, Any],
        optimize_result: Dict[str, Any],
        aoo_config: AOOConfig,
        task_id: Optional[str] = None,
        auto_adopt: bool = False,
        focus_areas: Optional[List[str]] = None,
    ) -> None:
        """将优化结果保存到 learning_paths / path_tasks / aoo_optimization_logs

        P2 重规划版本管理:
          - 若存在当前生效路径 (is_active=True)，新路径作为其子版本 (parent_path_id)
          - 新路径 version = 父版本 + 1
          - 新路径默认 is_active=False（待采纳）；auto_adopt=True 时直接采纳
          - 采纳时，旧生效路径置 is_active=False
        """
        engine = _get_engine()
        async with AsyncSession(engine) as session:
            try:
                # ── 查找当前生效路径作为父版本 ──
                parent_path = await session.scalar(
                    select(LearningPath)
                    .where(
                        LearningPath.student_id == student_id,
                        LearningPath.is_active == True,  # noqa: E712
                    )
                    .order_by(LearningPath.created_at.desc())
                    .limit(1)
                )
                parent_id = parent_path.id if parent_path else None
                new_version = (parent_path.version + 1) if parent_path else 1

                # ── 保存 LearningPath ──
                best_path = result.get("best_path", {})
                best_fitness = result.get("best_path_fitness", {})
                convergence = result.get("convergence", {})

                total_minutes = 0
                for day_data in best_path.get("days", []):
                    total_minutes += day_data.get("total_minutes", 0)

                # 规划类型语义标签（建议11）: 首轮=起点规划(baseline), 回流重规划=动态更新 vN
                plan_type = "baseline" if parent_id is None else f"update_v{new_version}"

                path = LearningPath(
                    student_id=student_id,
                    parent_path_id=parent_id,
                    version=new_version,
                    plan_type=plan_type,
                    # 默认待采纳；auto_adopt 时直接生效
                    is_active=bool(auto_adopt),
                    path_data={
                        "task_id": task_id,
                        "diagnosis_id": diagnosis_id,
                        "best_path": best_path,
                        "fitness_detail": optimize_result.get("fitness_detail"),
                        "alternative_paths": optimize_result.get("alternative_paths"),
                        "convergence_data": optimize_result.get("convergence_data"),
                        "pareto_front": result.get("pareto_front"),
                    },
                    total_duration=total_minutes,
                    estimated_completion_days=best_path.get("total_days"),
                    fitness_score=best_fitness.get("total_fitness"),
                )
                session.add(path)
                await session.flush()

                # 采纳：旧生效路径下线
                if auto_adopt and parent_path is not None:
                    parent_path.is_active = False
                    session.add(parent_path)

                # ── 保存 PathTasks ──
                task_order = 0
                for day_data in best_path.get("days", []):
                    day_idx = day_data.get("day", 1)
                    for task_data in day_data.get("tasks", []):
                        kp_id = task_data.get("knowledge_point", "")
                        try:
                            kp_uuid = UUID(kp_id)
                        except (ValueError, AttributeError):
                            continue

                        pt = PathTask(
                            path_id=path.id,
                            kp_id=kp_uuid,
                            day_index=day_idx,
                            order_index=task_order,
                            task_type=task_data.get("type", "reading"),
                            estimated_minutes=task_data.get("duration", 15),
                            completed=False,
                        )
                        session.add(pt)
                        task_order += 1

                # ── 保存 AOO 优化日志 ──
                iterations = convergence.get("iterations", [])
                best_fitnesses = convergence.get("best_fitness", [])
                avg_fitnesses = convergence.get("avg_fitness", [])
                diversities = convergence.get("diversity", [])

                for i in range(len(iterations)):
                    log_entry = AOOOptimizationLog(
                        student_id=student_id,
                        iteration=iterations[i] if i < len(iterations) else i + 1,
                        best_fitness=best_fitnesses[i] if i < len(best_fitnesses) else None,
                        avg_fitness=avg_fitnesses[i] if i < len(avg_fitnesses) else None,
                        diversity=diversities[i] if i < len(diversities) else None,
                        convergence_data={
                            "config": aoo_config.to_dict(),
                            "execution_time": optimize_result.get("execution_time"),
                        },
                    )
                    session.add(log_entry)

                # ── 写可观测性事件: 路径重规划 (含 reasoning) ──
                # P4: 真正解释"为什么路径变了" —— 引用薄弱点驱动 + 适应度变化
                weak_count = len(focus_areas or [])
                weak_hint = ""
                if focus_areas:
                    sample = ", ".join(str(k) for k in focus_areas[:3])
                    weak_hint = f"本次重规划主攻 {weak_count} 个薄弱知识点（如 {sample}）。"
                parent_fit = (
                    float(parent_path.fitness_score)
                    if parent_path and parent_path.fitness_score is not None
                    else None
                )
                new_fit = best_fitness.get("total_fitness")
                fit_hint = ""
                if isinstance(parent_fit, float) and isinstance(new_fit, (int, float)):
                    delta_fit = round(float(new_fit) - parent_fit, 4)
                    fit_hint = (
                        f"适应度由 v{parent_path.version} 的 {parent_fit} "
                        f"变化为 {new_fit}（{delta_fit:+.4f}）；"
                    )
                regen_reason = (
                    f"为什么路径变了：本轮对话测绘信号显示你的掌握度出现变化，"
                    f"{weak_hint}{fit_hint}"
                    f"因此生成新版本 v{new_version}"
                    + (f"（基于 v{parent_path.version}）" if parent_path else "（首个版本）")
                    + f"，适应度 {new_fit}。"
                    + ("已自动采纳，旧版本已下线。"
                       if auto_adopt
                       else "已生成待采纳版本，可在「路径」页查看具体改动后决定是否应用。")
                )
                session.add(
                    CognitiveProfileEvent(
                        student_id=student_id,
                        event_type="path_regenerate",
                        payload={
                            "path_id": str(path.id),
                            "parent_path_id": str(parent_id) if parent_id else None,
                            "version": new_version,
                            "auto_adopt": bool(auto_adopt),
                            "fitness_score": best_fitness.get("total_fitness"),
                            "task_count": task_order,
                        },
                        reasoning=regen_reason,
                    )
                )

                await session.commit()
                logger.info(
                    "AOO 结果已持久化: path_id=%s tasks=%d logs=%d",
                    path.id, task_order, len(iterations),
                )
            except Exception:
                await session.rollback()
                raise

    # ============================================================
    # 工具方法
    # ============================================================

    @staticmethod
    async def _safe_callback(
        cb: callable,
        progress: float,
        current_iter: int,
        max_iter: int,
        best_f: float,
    ) -> None:
        """安全调用进度回调"""
        try:
            if asyncio.iscoroutinefunction(cb):
                await cb(progress, current_iter, max_iter, best_f)
            else:
                cb(progress, current_iter, max_iter, best_f)
        except Exception as exc:
            logger.warning("进度回调异常: %s", exc)

    @staticmethod
    def _empty_result(diagnosis_id: str) -> Dict[str, Any]:
        """无数据时的空结果"""
        return {
            "best_path": {
                "days": [], "total_days": 0, "total_tasks": 0,
                "total_estimated_hours": 0, "total_fitness": 0,
            },
            "fitness_detail": {},
            "alternative_paths": [],
            "convergence_data": {
                "iterations": [], "best_fitness": [], "avg_fitness": [],
                "diversity": [], "median_fitness": [], "q1_fitness": [],
                "q3_fitness": [], "population_snapshots": None,
                "metadata": {
                    "algorithm": "AOO", "population_size": 0, "elite_count": 0,
                    "convergence_rate": 0, "convergence_iteration": 0,
                    "total_time_seconds": 0,
                },
            },
            "pareto_front": {"size": 0, "has_data": False},
            "execution_time": 0,
        }
