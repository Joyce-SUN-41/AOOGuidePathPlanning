"""AOO (Animated Oat Optimization) 算法服务

集成核心引擎、适应度计算器、配置模块，对外暴露统一接口。

使用方式:
    result = await aoo_service.optimize(diagnosis_id="...")
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

import numpy as np

from app.services.aoo.aoo_config import AOOConfig, default_config
from app.services.aoo.aoo_engine import AOOEngine, OptimizationResult
from app.services.aoo.fitness_calculator import (
    FitnessCalculator,
    FitnessResult,
    ParetoFront,
    build_fitness_calculator,
)

logger = logging.getLogger(__name__)


class AOOService:
    """AOO 算法核心服务

    负责:
      1. 从诊断数据构建适应度计算器
      2. 初始化并运行 AOO 优化引擎
      3. 提取 Pareto 前沿，生成 3 条差异化路径
      4. 将优化结果转换为 API 响应格式
    """

    def __init__(self, config: Optional[AOOConfig] = None):
        self.config = config or default_config

    async def optimize(
        self,
        diagnosis_id: Optional[str] = None,
        knowledge_points: Optional[list] = None,
        student_mastery: Optional[Dict[str, float]] = None,
        focus_areas: Optional[list] = None,
        preferences: Optional[dict] = None,
        config: Optional[AOOConfig] = None,
        iteration_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """执行 AOO 优化算法

        Args:
            diagnosis_id: 诊断结果 ID
            knowledge_points: 知识点列表 (dict 格式)
            student_mastery: 学生掌握度字典
            focus_areas: 重点关注的薄弱知识点
            preferences: 用户偏好设置 (max_days, intensity, max_daily_minutes 等)
            config: 自定义配置 (覆盖默认值)
            iteration_callback: 每代回调 callable(iter, best_f, avg_f, diversity)

        Returns:
            包含 best_path, alternative_paths, pareto_front, convergence 等字段的字典
        """
        # ---- 合并配置 ----
        cfg = self._merge_config(preferences, config)

        logger.info(
            "AOOService.optimize starting | diagnosis_id=%s population=%d max_iter=%d dim=%d",
            diagnosis_id,
            cfg.population_size,
            cfg.max_iterations,
            len(knowledge_points) if knowledge_points else 0,
        )

        # ---- 处理知识点数据 ----
        kp_list = knowledge_points or []
        if kp_list:
            cfg.dim = len(kp_list)

        if not kp_list:
            logger.warning("AOOService.optimize: 无知识点数据, 返回空结果")
            return self._empty_response(diagnosis_id)

        # ---- 构建适应度计算器 ----
        max_daily_hours = self._extract_max_daily_hours(preferences)

        fitness_calc = build_fitness_calculator(
            knowledge_points=kp_list,
            student_mastery=student_mastery or {},
            focus_areas=focus_areas or [],
            max_daily_hours=max_daily_hours,
            config=cfg,
        )

        # ---- 运行 AOO 引擎 ----
        engine = AOOEngine(config=cfg, fitness_calculator=fitness_calc)
        result = engine.optimize(on_iteration=iteration_callback)

        logger.info(
            "AOO engine completed | best_f=%.6f time=%.2fs iter=%d",
            result.best_fitness, result.total_time_seconds, result.total_iterations,
        )

        # ---- 提取 Pareto 前沿 ----
        pareto_front = self._extract_pareto_front(result, fitness_calc)

        # ---- 构建 3 条差异化路径 ----
        best_path = self._build_best_path(result, fitness_calc)
        alternative_paths = self._build_alternative_paths(pareto_front, fitness_calc)

        # ---- 构建 API 响应 ----
        response = self._build_response(result, fitness_calc, cfg, best_path, alternative_paths)
        response["diagnosis_id"] = diagnosis_id
        response["pareto_front"] = self._serialize_pareto_front(pareto_front)

        logger.info(
            "AOOService.optimize completed | best_f=%.6f pareto_size=%d alt_paths=%d",
            result.best_fitness, pareto_front.size,
            len(alternative_paths),
        )

        return response

    async def run_benchmark(
        self,
        knowledge_points: list,
        student_mastery: Dict[str, float],
        n_runs: int = 5,
        config: Optional[AOOConfig] = None,
    ) -> Dict[str, Any]:
        """多次运行取平均 (用于基准测试)"""
        cfg = config or self.config
        cfg.dim = len(knowledge_points)

        fitness_calc = build_fitness_calculator(
            knowledge_points=knowledge_points,
            student_mastery=student_mastery,
            config=cfg,
        )

        best_fitnesses = []
        times = []
        feasible_counts = []
        pareto_sizes = []

        for run_id in range(1, n_runs + 1):
            cfg_run = AOOConfig(**{**cfg.to_dict(), "seed": cfg.seed + run_id})
            engine = AOOEngine(config=cfg_run, fitness_calculator=fitness_calc)
            result = engine.optimize()

            best_fitnesses.append(result.best_fitness)
            times.append(result.total_time_seconds)

            # 统计可行解
            _, final_results = fitness_calc.evaluate_population(result.final_population)
            feasible = sum(1 for r in final_results if r.is_feasible)
            feasible_counts.append(feasible)

            pf = fitness_calc.compute_pareto_front(
                final_results, result.final_population
            )
            pareto_sizes.append(pf.size)

        mean_f = sum(best_fitnesses) / len(best_fitnesses)
        std_f = (sum((f - mean_f)**2 for f in best_fitnesses) / len(best_fitnesses))**0.5
        mean_t = sum(times) / len(times)

        return {
            "n_runs": n_runs,
            "best_fitness_mean": mean_f,
            "best_fitness_std": std_f,
            "best_fitnesses": best_fitnesses,
            "time_mean": mean_t,
            "feasible_count_mean": sum(feasible_counts) / len(feasible_counts),
            "pareto_size_mean": sum(pareto_sizes) / len(pareto_sizes),
        }

    # ============================================================
    # 私有方法
    # ============================================================

    def _merge_config(
        self,
        preferences: Optional[dict] = None,
        config: Optional[AOOConfig] = None,
    ) -> AOOConfig:
        """合并用户偏好到配置"""
        cfg = config or AOOConfig(**{**self.config.to_dict()})

        if preferences:
            for key in ("population_size", "max_iterations"):
                if key in preferences and preferences[key] is not None:
                    setattr(cfg, key, preferences[key])
            if "alpha" in preferences:
                cfg.alpha = float(preferences["alpha"])
            if "beta" in preferences:
                cfg.beta = float(preferences["beta"])

        return cfg

    @staticmethod
    def _extract_max_daily_hours(preferences: Optional[dict]) -> float:
        """从用户偏好中提取每日最大学习时长 (小时)"""
        if preferences:
            if "max_daily_minutes" in preferences and preferences["max_daily_minutes"] is not None:
                return preferences["max_daily_minutes"] / 60.0
            if "max_daily_hours" in preferences and preferences["max_daily_hours"] is not None:
                return float(preferences["max_daily_hours"])
        return 4.0

    def _extract_pareto_front(
        self,
        result: OptimizationResult,
        fitness_calc: FitnessCalculator,
    ) -> ParetoFront:
        """从最终种群提取 Pareto 前沿"""
        final_pop = result.final_population
        if final_pop is None or final_pop.shape[0] == 0:
            logger.warning("最终种群为空, 跳过 Pareto 分析")
            return ParetoFront()

        # 使用严格模式评估最终种群
        N = final_pop.shape[0]
        strict_results = []
        feasible_count = 0
        for i in range(N):
            fr = fitness_calc.evaluate_strict(final_pop[i])
            strict_results.append(fr)
            if fr.is_feasible:
                feasible_count += 1

        logger.info(
            "最终种群分析 | 总数=%d 可行解=%d (%.1f%%)",
            N, feasible_count, 100 * feasible_count / max(N, 1),
        )

        pf = fitness_calc.compute_pareto_front(strict_results, final_pop)

        if pf.has_data:
            efficiency = pf.efficiency_result
            balanced = pf.balanced_result
            robust = pf.robust_result
            logger.info(
                "Pareto 路径分类完成:\n"
                "  效率型: fitness=%.4f learn=%.4f cognitive=%.4f\n"
                "  平衡型: fitness=%.4f learn=%.4f cognitive=%.4f\n"
                "  稳健型: fitness=%.4f learn=%.4f cognitive=%.4f",
                efficiency.total_fitness if efficiency else float("nan"),
                efficiency.learning_effect if efficiency else float("nan"),
                efficiency.cognitive_load_score if efficiency else float("nan"),
                balanced.total_fitness if balanced else float("nan"),
                balanced.learning_effect if balanced else float("nan"),
                balanced.cognitive_load_score if balanced else float("nan"),
                robust.total_fitness if robust else float("nan"),
                robust.learning_effect if robust else float("nan"),
                robust.cognitive_load_score if robust else float("nan"),
            )
        else:
            logger.warning("Pareto 前沿为空 (无可行解)")

        return pf

    def _build_best_path(
        self,
        result: OptimizationResult,
        fitness_calc: FitnessCalculator,
    ) -> Dict[str, Any]:
        """从最优位置构建学习路径 (BestPath schema 格式)"""
        return self._position_to_path_dict(
            result.best_position, fitness_calc, "optimal"
        )

    def _build_alternative_paths(
        self,
        pareto_front: ParetoFront,
        fitness_calc: FitnessCalculator,
    ) -> List[Dict[str, Any]]:
        """从 Pareto 前沿构建 3 条差异化路径"""
        paths = []

        # 效率型
        if pareto_front.efficiency_result is not None and pareto_front.efficiency_idx >= 0:
            pos = pareto_front.positions[pareto_front.efficiency_idx]
            path = self._position_to_path_dict(pos, fitness_calc, "efficiency")
            path["fitness_result"] = self._fitness_result_to_dict(
                pareto_front.efficiency_result
            )
            paths.append(path)

        # 平衡型
        if (pareto_front.balanced_result is not None
                and pareto_front.balanced_idx >= 0
                and pareto_front.balanced_idx != pareto_front.efficiency_idx):
            pos = pareto_front.positions[pareto_front.balanced_idx]
            path = self._position_to_path_dict(pos, fitness_calc, "balanced")
            path["fitness_result"] = self._fitness_result_to_dict(
                pareto_front.balanced_result
            )
            paths.append(path)

        # 稳健型
        if (pareto_front.robust_result is not None
                and pareto_front.robust_idx >= 0
                and pareto_front.robust_idx != pareto_front.efficiency_idx
                and pareto_front.robust_idx != pareto_front.balanced_idx):
            pos = pareto_front.positions[pareto_front.robust_idx]
            path = self._position_to_path_dict(pos, fitness_calc, "robust")
            path["fitness_result"] = self._fitness_result_to_dict(
                pareto_front.robust_result
            )
            paths.append(path)

        return paths

    def _position_to_path_dict(
        self,
        position: np.ndarray,
        fitness_calc: FitnessCalculator,
        path_type: str = "optimal",
    ) -> Dict[str, Any]:
        """将位置向量转换为路径字典 (BestPath schema)"""
        kps = fitness_calc.kps
        order = fitness_calc._decode_order(position)

        total_kps = len(order)
        total_hours = sum(kp.estimated_hours for kp in kps)

        # 计算学习天数
        suggested_days = max(
            1,
            int(np.ceil(total_hours / fitness_calc.config.daily_load_threshold_hours)),
            int(np.ceil(total_kps / 5)),
        )
        num_days = max(3, min(suggested_days, 14))
        kps_per_day = max(1, int(np.ceil(total_kps / num_days)))

        days = []
        total_tasks = 0
        total_minutes_sum = 0.0

        for day_idx in range(num_days):
            start = day_idx * kps_per_day
            end = min(start + kps_per_day, total_kps)

            tasks = []
            day_minutes = 0
            day_difficulties = []

            for pos_idx in range(start, end):
                kp_idx = order[pos_idx]
                if kp_idx >= len(kps):
                    continue
                kp = kps[kp_idx]
                duration_min = int(kp.estimated_hours * 60)

                tasks.append({
                    "name": kp.name or f"知识点 {kp.id}",
                    "duration": duration_min,
                    "type": self._map_layer_to_type(kp.layer),
                    "knowledge_point": kp.id,
                    "difficulty": int(kp.difficulty),
                })
                day_minutes += duration_min
                day_difficulties.append(kp.difficulty)
                total_tasks += 1

            avg_d = (
                sum(day_difficulties) / len(day_difficulties)
                if day_difficulties else 0
            )

            days.append({
                "day": day_idx + 1,
                "tasks": tasks,
                "total_minutes": day_minutes,
                "avg_difficulty": round(avg_d, 1),
            })

            total_minutes_sum += day_minutes

        return {
            "days": days,
            "total_days": num_days,
            "total_tasks": total_tasks,
            "total_estimated_hours": round(total_minutes_sum / 60.0, 1),
            "path_type": path_type,
        }

    def _build_response(
        self,
        result: OptimizationResult,
        fitness_calc: FitnessCalculator,
        config: AOOConfig,
        best_path: Dict[str, Any],
        alternative_paths: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """将优化结果转换为 API 响应格式"""
        conv = result.convergence

        max_best = max(conv.best_fitness) if conv.best_fitness else 0
        convergence_rate = (
            conv.best_fitness[-1] / max_best if max_best != 0 else 0
        )

        threshold = 0.95 * max_best
        convergence_iter = result.total_iterations
        for idx, fit in enumerate(conv.best_fitness):
            if fit >= threshold:
                convergence_iter = idx + 1
                break

        # 评估最佳路径的详细得分
        best_fr = fitness_calc.evaluate_strict(result.best_position)

        # 序列化种群快照 (用于前端粒子轨迹动画)
        population_snapshots = [
            {
                "iteration": snap.iteration,
                "fitnessValues": snap.fitness_values,
                "positionsX": snap.positions_x,
                "positionsY": snap.positions_y,
                "colors": snap.colors,
                "bestIndex": snap.best_index,
            }
            for snap in conv.snapshots
        ]

        return {
            "best_path": best_path,
            "best_path_fitness": self._fitness_result_to_dict(best_fr),
            "alternative_paths": alternative_paths,
            "convergence": {
                "iterations": conv.iterations,
                "best_fitness": conv.best_fitness,
                "avg_fitness": conv.avg_fitness,
                "diversity": conv.diversity,
                "median_fitness": conv.median_fitness,
                "q1_fitness": conv.q1_fitness,
                "q3_fitness": conv.q3_fitness,
                "population_snapshots": population_snapshots,
                "metadata": {
                    "algorithm": "AOO",
                    "population_size": config.population_size,
                    "elite_count": 1,
                    "convergence_rate": round(convergence_rate, 4),
                    "convergence_iteration": convergence_iter,
                    "total_time_seconds": round(result.total_time_seconds, 2),
                },
            },
        }

    @staticmethod
    def _fitness_result_to_dict(fr: FitnessResult) -> Dict[str, Any]:
        """将 FitnessResult 序列化为字典"""
        d = {
            "total_fitness": round(fr.total_fitness, 6),
            "learning_effect": round(fr.learning_effect, 6),
            "coverage": round(fr.coverage, 4),
            "mastery_improvement": round(fr.mastery_improvement, 4),
            "avg_final_mastery": round(fr.avg_final_mastery, 4),
            "cognitive_load_score": round(fr.cognitive_load_score, 6),
            "daily_load_score": round(fr.daily_load_score, 6),
            "difficulty_density": round(fr.difficulty_density, 4),
            "prerequisite_violations": fr.prerequisite_violations,
            "is_feasible": fr.is_feasible,
            "path_type": fr.path_type,
        }
        if fr.cognitive_detail:
            d["cognitive_detail"] = {
                "avg_daily_load_hours": round(fr.cognitive_detail.avg_daily_load_hours, 2),
                "max_daily_load_hours": round(fr.cognitive_detail.max_daily_load_hours, 2),
                "overload_ratio": round(fr.cognitive_detail.overload_ratio, 4),
                "difficulty_density_score": round(fr.cognitive_detail.difficulty_density_score, 4),
            }
        if fr.learning_detail:
            d["learning_detail"] = {
                "coverage": round(fr.learning_detail.coverage, 4),
                "avg_final_mastery": round(fr.learning_detail.avg_final_mastery, 4),
            }
        return d

    @staticmethod
    def _serialize_pareto_front(pf: ParetoFront) -> Dict[str, Any]:
        """序列化 Pareto 前沿"""
        return {
            "size": pf.size,
            "has_data": pf.has_data,
            "efficiency_idx": pf.efficiency_idx,
            "balanced_idx": pf.balanced_idx,
            "robust_idx": pf.robust_idx,
            "fitness_results": [
                AOOService._fitness_result_to_dict(r)
                for r in pf.fitness_results
            ],
        }

    @staticmethod
    def _map_layer_to_type(layer: str) -> str:
        """层级 → 任务类型映射"""
        mapping = {
            "basic": "reading",
            "core": "video",
            "advanced": "project",
        }
        return mapping.get(layer, "exercise")

    @staticmethod
    def _empty_response(diagnosis_id: Optional[str]) -> Dict[str, Any]:
        """空结果响应"""
        return {
            "diagnosis_id": diagnosis_id,
            "best_path": {"days": [], "total_days": 0, "total_tasks": 0, "total_estimated_hours": 0, "path_type": "optimal"},
            "best_path_fitness": {"total_fitness": 0, "learning_effect": 0, "is_feasible": True},
            "alternative_paths": [],
            "pareto_front": {"size": 0, "has_data": False},
            "convergence": {
                "iterations": [], "best_fitness": [], "avg_fitness": [],
                "diversity": [], "median_fitness": [], "q1_fitness": [], "q3_fitness": [],
                "population_snapshots": None,
                "metadata": {"algorithm": "AOO", "convergence_rate": 0, "convergence_iteration": 0},
            },
        }


# ============================================================
# 全局服务实例
# ============================================================
aoo_service = AOOService()
