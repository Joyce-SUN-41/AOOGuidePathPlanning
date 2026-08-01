"""AOO 路径优化服务层 — 数据加载 / 算法调用 / 结果持久化

负责:
  1. 从数据库加载知识点 & 诊断数据
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
    ) -> Dict[str, Any]:
        """执行完整 AOO 优化工作流

        Args:
            diagnosis_id: 诊断记录 ID
            student_id: 学生用户 ID
            mastery_levels: 知识点掌握度映射 {kp_id: value ∈ [0,1]}
            cognitive_load: 综合认知负荷指数
            config: 可选的 AOO 超参数覆盖
            progress_callback: 进度回调 callable(progress_pct, current_iter, max_iter, best_f)
            iteration_callback: 每代回调 callable(iter, best_f, avg_f, diversity)，用于实时收敛上报
            task_id: Celery 任务 ID (用于 DB 关联)

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
        full_mastery = await self._merge_student_mastery(
            student_id, mastery_levels
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

        # 6. 确定薄弱知识点
        focus_areas = [
            kp_id for kp_id, v in full_mastery.items()
            if v < 0.6
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
            "AOO 优化完成: diagnosis=%s total=%.2fs best_f=%.6f",
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
    ) -> Dict[str, float]:
        """合并请求中的掌握度与数据库中的历史掌握度"""
        merged = dict(incoming)

        try:
            engine = _get_engine()
            async with AsyncSession(engine) as session:
                result = await session.execute(
                    select(StudentKnowledge).where(
                        StudentKnowledge.student_id == UUID(student_id)
                    )
                )
                records = result.scalars().all()
                for r in records:
                    kp_id = str(r.kp_id)
                    if kp_id not in merged:
                        merged[kp_id] = float(r.mastery_level)
        except Exception as exc:
            logger.warning("加载历史掌握度失败: %s", exc)

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
    ) -> None:
        """将优化结果保存到 learning_paths / path_tasks / aoo_optimization_logs"""
        engine = _get_engine()
        async with AsyncSession(engine) as session:
            try:
                # ── 保存 LearningPath ──
                best_path = result.get("best_path", {})
                best_fitness = result.get("best_path_fitness", {})
                convergence = result.get("convergence", {})

                total_minutes = 0
                for day_data in best_path.get("days", []):
                    total_minutes += day_data.get("total_minutes", 0)

                path = LearningPath(
                    student_id=student_id,
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
