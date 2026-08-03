"""AOO 适应度计算器 — 教育场景定制 (增强版)

将个体位置向量解码为学习路径方案，计算多维适应度分数，
支持 Pareto 前沿提取与路径类型分类。

核心公式:
  learning_effect = coverage × w_cov + avg_final_mastery × w_mst    (目标1: 最大化)
  cognitive_load_score = mean(daily_load) / threshold + density × w_density  (目标2: 最小化)
  fitness = α × learning_effect - β × cognitive_load_score
  若前置依赖违反 → fitness = -1e9 (硬约束)

Pareto 多目标: 返回 3 条差异化路径 (效率型 / 平衡型 / 稳健型)
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.services.aoo.aoo_config import AOOConfig, default_config

logger = logging.getLogger(__name__)


# ============================================================
# 数据类型定义
# ============================================================


@dataclass
class KnowledgePointMeta:
    """知识点元信息 (轻量级, 不依赖 ORM)"""

    id: str
    name: str = ""
    difficulty: float = 1.0       # 难度: 1-5
    layer: str = "core"            # 层级: basic / core / advanced
    prerequisites: List[str] = field(default_factory=list)  # 前置知识点 id 列表
    estimated_hours: float = 1.0   # 预估学习时长 (小时)


@dataclass
class StudentProfile:
    """学生画像"""

    current_mastery: Dict[str, float] = field(default_factory=dict)
    max_daily_hours: float = 4.0
    learning_speed: float = 1.0
    focus_areas: List[str] = field(default_factory=list)


@dataclass
class LearningEffectDetail:
    """学习效果详细分解"""

    coverage: float                     # 知识图谱覆盖率 [0, 1]
    avg_final_mastery: float            # 平均最终掌握度 [0, 1]
    per_kp_gains: List[float] = field(default_factory=list)   # 每题知识点掌握度提升列表
    per_kp_final_mastery: List[float] = field(default_factory=list)  # 每题最终掌握度
    score: float = 0.0                  # 加权总分


@dataclass
class CognitiveLoadDetail:
    """认知负荷详细分解"""

    avg_daily_load_hours: float         # 平均单日学习量 (小时)
    max_daily_load_hours: float         # 最大单日学习量
    overload_ratio: float               # 超负荷天数占比
    difficulty_density_score: float     # 难度密集度得分
    score: float = 0.0                  # 综合认知负荷得分


@dataclass
class FitnessResult:
    """适应度计算结果 (增强版)"""

    # ---- 总适应度 ----
    total_fitness: float

    # ---- 学习效果 ----
    learning_effect: float
    coverage: float
    mastery_improvement: float          # 兼容旧字段: avg_final_mastery
    avg_final_mastery: float = 0.0

    # ---- 认知负荷 ----
    cognitive_load_score: float = 0.0
    daily_load: List[float] = field(default_factory=list)
    daily_load_score: float = 0.0       # average(daily_load) / threshold
    difficulty_density: float = 0.0     # 难度密集度得分

    # ---- 约束 ----
    prerequisite_violations: int = 0
    is_feasible: bool = True

    # ---- 多目标 ----
    path_type: str = ""                 # efficiency / balanced / robust

    # ---- 学习效果 & 认知负荷详情 (可选) ----
    learning_detail: Optional[LearningEffectDetail] = None
    cognitive_detail: Optional[CognitiveLoadDetail] = None


@dataclass
class ParetoFront:
    """Pareto 前沿 — 一组非支配解"""

    positions: List[np.ndarray] = field(default_factory=list)         # 非支配个体位置
    fitness_results: List[FitnessResult] = field(default_factory=list)
    efficiency_idx: int = -1           # 效率型在列表中的索引
    balanced_idx: int = -1              # 平衡型在列表中的索引
    robust_idx: int = -1                # 稳健型在列表中的索引

    @property
    def efficiency_result(self) -> Optional[FitnessResult]:
        if 0 <= self.efficiency_idx < len(self.fitness_results):
            return self.fitness_results[self.efficiency_idx]
        return None

    @property
    def balanced_result(self) -> Optional[FitnessResult]:
        if 0 <= self.balanced_idx < len(self.fitness_results):
            return self.fitness_results[self.balanced_idx]
        return None

    @property
    def robust_result(self) -> Optional[FitnessResult]:
        if 0 <= self.robust_idx < len(self.fitness_results):
            return self.fitness_results[self.robust_idx]
        return None

    @property
    def size(self) -> int:
        return len(self.positions)

    @property
    def has_data(self) -> bool:
        return len(self.positions) > 0


# ============================================================
# FitnessCalculator — 核心类
# ============================================================


class FitnessCalculator:
    """教育场景适应度计算器 (增强版)

    将 AOO 个体位置向量解码为学习路径方案，计算综合适应度。

    解码规则: 按 position 值从小到大排序 → 得到学习顺序
    值越小 → 越早学; 值越大 → 越晚学。

    适应度公式:
      fitness = α × learning_effect - β × cognitive_load_score
      learning_effect = 0.3 × coverage + 0.7 × avg_final_mastery
      cognitive_load_score = avg_daily_load / threshold + 0.3 × difficulty_density

    硬约束: 前置依赖违反 → fitness = -1e9
    """

    # ----------------------------------------------------------------
    # 初始化
    # ----------------------------------------------------------------

    def __init__(
        self,
        knowledge_points: List[KnowledgePointMeta],
        student_profile: StudentProfile,
        config: Optional[AOOConfig] = None,
    ):
        self.kps = knowledge_points
        self.student = student_profile
        self.config = config or default_config

        # 构建快速查找索引: kp_id → 数组下标
        self.kp_index: Dict[str, int] = {
            kp.id: i for i, kp in enumerate(self.kps)
        }

        # 缓存评估中间数据以避免重复计算
        self._eval_cache: Dict[int, FitnessResult] = {}

        logger.debug(
            "FitnessCalculator 初始化 | kps=%d mastery_entries=%d max_daily_h=%.1f "
            "w_cov=%.2f w_mst=%.2f α=%.2f β=%.2f forgetting=%.2f",
            len(self.kps),
            len(self.student.current_mastery),
            self.student.max_daily_hours,
            self.config.coverage_weight,
            self.config.mastery_weight,
            self.config.alpha,
            self.config.beta,
            self.config.forgetting_factor,
        )

    # ============================================================
    # 公共接口
    # ============================================================

    def evaluate(
        self, position: np.ndarray, strict: bool = False
    ) -> FitnessResult:
        """计算单个个体的适应度

        六步流程:
          1. 解码位置 → 学习顺序
          2. 计算覆盖率
          3. 计算掌握度增益 (含遗忘曲线)
          4. 汇总学习效果
          5. 计算认知负荷得分
          6. 前置依赖检查 + 综合适应度

        Args:
            position: 个体位置向量 shape=(Dim,), 值域 [LB, UB]
            strict: True = 硬约束 (不可行→fitness=-1e9), False = 梯度惩罚 (用于优化搜索)

        Returns:
            FitnessResult 包含各项详细分数
        """
        # ---- Step 1: 解码 ----
        order = self._decode_order(position)

        logger.debug("evaluate | strict=%s order=%s",
                     strict, order[:5] if len(order) > 5 else order)

        # ---- Step 2: 覆盖率 ----
        coverage = self._calculate_coverage(order)
        logger.debug("  coverage=%.4f", coverage)

        # ---- Step 3: 掌握度增益 (含遗忘曲线) ----
        learning_detail = self._calculate_learning_effect_detail(order)
        logger.debug(
            "  learning_effect=%.4f (cov=%.4f×%.2f + avg_mst=%.4f×%.2f)",
            learning_detail.score, coverage,
            self.config.coverage_weight,
            learning_detail.avg_final_mastery, self.config.mastery_weight,
        )

        # ---- Step 4: 认知负荷 ----
        daily_load = self._calculate_daily_load(order)
        cognitive_detail = self._calculate_cognitive_load_detail(daily_load, order)
        logger.debug(
            "  cognitive_load=%.4f (daily_avg=%.2f/%.1f + density=%.4f×%.2f)",
            cognitive_detail.score,
            cognitive_detail.avg_daily_load_hours, self.config.daily_load_threshold_hours,
            cognitive_detail.difficulty_density_score, self.config.difficulty_density_weight,
        )

        # ---- Step 5: 前置依赖检查 ----
        violations = self._check_prerequisites(order)
        is_feasible = violations == 0
        logger.debug("  violations=%d feasible=%s", violations, is_feasible)

        # ---- Step 6: 综合适应度 ----
        base_fitness = (
            self.config.alpha * learning_detail.score
            - self.config.beta * cognitive_detail.score
        )

        if is_feasible:
            total_fitness = base_fitness
        elif strict:
            # 硬约束模式: 不可行解 → 极大负值 (用于 Pareto 前沿提取)
            total_fitness = self.config.prerequisite_penalty
        else:
            # 梯度惩罚模式: 每次违反扣 100 分, 引导搜索向可行区域 (用于优化迭代)
            violation_gradient_penalty = 100.0
            total_fitness = base_fitness - violations * violation_gradient_penalty

        logger.debug("  total_fitness=%.6f (base=%.6f)", total_fitness, base_fitness)

        return FitnessResult(
            total_fitness=float(total_fitness),
            learning_effect=float(learning_detail.score),
            coverage=float(coverage),
            mastery_improvement=float(learning_detail.avg_final_mastery),
            avg_final_mastery=float(learning_detail.avg_final_mastery),
            cognitive_load_score=float(cognitive_detail.score),
            daily_load=daily_load,
            daily_load_score=float(cognitive_detail.avg_daily_load_hours
                                   / max(self.config.daily_load_threshold_hours, 0.01)),
            difficulty_density=float(cognitive_detail.difficulty_density_score),
            prerequisite_violations=violations,
            is_feasible=is_feasible,
            learning_detail=learning_detail,
            cognitive_detail=cognitive_detail,
        )

    def evaluate_strict(self, position: np.ndarray) -> FitnessResult:
        """严格模式评估 (硬约束, 用于 Pareto 前沿提取)

        前置依赖违反 → fitness = -1e9, is_feasible = False
        """
        return self.evaluate(position, strict=True)

    def evaluate_population(
        self,
        population: np.ndarray,
    ) -> Tuple[np.ndarray, List[FitnessResult]]:
        """批量评估种群 (非严格模式, 用于优化迭代)

        Args:
            population: shape=(N, Dim)

        Returns:
            (fitness_array, result_list)
        """
        N = population.shape[0]
        fitness_values = np.zeros(N)
        results: List[FitnessResult] = []

        for i in range(N):
            fr = self.evaluate(population[i], strict=False)
            fitness_values[i] = fr.total_fitness
            results.append(fr)

        return fitness_values, results

    def compute_pareto_front(
        self,
        results: List[FitnessResult],
        positions: Optional[np.ndarray] = None,
    ) -> ParetoFront:
        """从一组评估结果中提取 Pareto 前沿

        双目标优化:
          obj1 = learning_effect    (最大化)
          obj2 = -cognitive_load_score  (最大化, 等价于最小化认知负荷)

        非支配排序后, 提取 3 条代表性路径:
          - 效率型 (efficiency): learning_effect 最高
          - 平衡型 (balanced):  距理想点最近
          - 稳健型 (robust):    cognitive_load_score 最低

        Args:
            results: 评估结果列表
            positions: 对应的个体位置矩阵 shape=(N, Dim), 可选

        Returns:
            ParetoFront 对象
        """
        if not results:
            logger.warning("compute_pareto_front: 空结果集, 返回空 Pareto 前沿")
            return ParetoFront()

        # 只考虑可行解
        feasible_indices = [i for i, r in enumerate(results) if r.is_feasible]
        feasible_count = len(feasible_indices)

        logger.info(
            "Pareto 分析 | 总数=%d 可行解=%d (%.1f%%)",
            len(results),
            feasible_count,
            100 * feasible_count / max(len(results), 1),
        )

        if feasible_count == 0:
            logger.warning("compute_pareto_front: 无可非解")
            return ParetoFront()

        # 提取可行解的目标值
        obj_learning = np.array([results[i].learning_effect for i in feasible_indices])
        obj_cognitive_neg = np.array([
            -results[i].cognitive_load_score for i in feasible_indices
        ])

        # 非支配排序
        non_dominated_mask = self._non_dominated_sort(obj_learning, obj_cognitive_neg)
        pareto_local_indices = np.where(non_dominated_mask)[0]

        logger.info(
            "Pareto 前沿 | 候选=%d 非支配解=%d",
            feasible_count,
            len(pareto_local_indices),
        )

        # 构建 Pareto 前沿
        pareto_abs_indices = [feasible_indices[i] for i in pareto_local_indices]
        pareto_results = [results[i] for i in pareto_abs_indices]

        pf = ParetoFront()

        if positions is not None:
            pf.positions = [positions[i].copy() for i in pareto_abs_indices]
        pf.fitness_results = pareto_results

        # 按 learning_effect 排序
        sort_order = np.argsort([
            r.learning_effect for r in pareto_results
        ])  # 升序
        pf.fitness_results = [pareto_results[i] for i in sort_order]
        if pf.positions:
            pf.positions = [pf.positions[i] for i in sort_order]

        # ---- 路径分类 ----
        pf = self._classify_pareto_paths(pf)

        # 限制最大数量
        if len(pf.fitness_results) > self.config.pareto_max_paths:
            # 均匀采样保留
            indices = np.linspace(
                0, len(pf.fitness_results) - 1,
                self.config.pareto_max_paths, dtype=int
            )
            pf.fitness_results = [pf.fitness_results[i] for i in indices]
            if pf.positions:
                pf.positions = [pf.positions[i] for i in indices]
            # 重新分类
            pf = self._classify_pareto_paths(pf)

        logger.info(
            "Pareto 分类 | efficiency=%d balanced=%d robust=%d total=%d",
            pf.efficiency_idx,
            pf.balanced_idx,
            pf.robust_idx,
            pf.size,
        )

        return pf

    # ============================================================
    # Step 1: 解码路径
    # ============================================================

    def _decode_order(self, position: np.ndarray) -> List[int]:
        """将位置向量解码为学习顺序索引列表

        按 position 值从小到大排序, 得到学习顺序。
        值越小 → 越早学; 值越大 → 越晚学。

        处理 NaN/Inf: 替换为默认值后 clip 到 [LB, UB]。
        """
        safe_position = np.nan_to_num(position, nan=1.0, posinf=1.0, neginf=0.0)
        safe_position = np.clip(safe_position, self.config.lb, self.config.ub)
        order = list(np.argsort(safe_position))
        return order

    # ============================================================
    # Step 2: 知识覆盖率
    # ============================================================

    def _calculate_coverage(self, order: List[int]) -> float:
        """计算知识图谱覆盖率

        覆盖率 = 被纳入学习路径的知识点数 / 总知识点数
        当前实现: order 总是包含所有索引, 返回 1.0
        (未来可支持部分知识点跳过)
        """
        if len(self.kps) == 0:
            return 0.0
        covered = len(order)
        return covered / len(self.kps)

    # ============================================================
    # Step 3: 学习效果评估 (含遗忘曲线)
    #
    # 掌握度模型:
    #   final_mastery(i) = min(1.0, current_mastery(i) + learning_gain(i))
    #   learning_gain(i) = base_gain × (1 - forgetting_factor ^ time_interval)
    #
    # time_interval: 该知识点在路径中的位置 / 总知识点数
    #   (靠前的知识点有更多时间巩固, 同时遗忘也相对较少)
    #
    #   更精确的模型:
    #   - 前置知识点的掌握度影响后续知识点的学习增益
    #   - 遗忘因子模拟艾宾浩斯遗忘曲线
    #   - learning_speed 调节学习速度
    # ============================================================

    def _calculate_learning_effect_detail(
        self, order: List[int]
    ) -> LearningEffectDetail:
        """计算学习效果详细分解

        完整流程:
          1. 计算覆盖率
          2. 对每个知识点计算最终掌握度:
             a. 获取当前掌握度
             b. 计算学习增益 (考虑遗忘 + 前置依赖传递)
             c. final = min(1.0, current + gain)
          3. 汇总: 加权平均掌握度
          4. 得分 = coverage × w_cov + avg_final_mastery × w_mst
        """
        coverage = self._calculate_coverage(order)
        Dim = max(len(self.kps), 1)
        T = max(len(order), 1)

        per_kp_gains: List[float] = []
        per_kp_final: List[float] = []

        for rank, kp_idx in enumerate(order):
            if kp_idx >= Dim:
                per_kp_gains.append(0.0)
                per_kp_final.append(0.0)
                continue

            kp = self.kps[kp_idx]
            current_mastery = self.student.current_mastery.get(kp.id, 0.0)

            # ---- 计算学习增益 ----
            gain = self._compute_kp_learning_gain(
                kp=kp,
                rank=rank,
                total_ranks=T,
                learned_ids=set(
                    self.kps[order[j]].id
                    for j in range(rank)
                    if order[j] < Dim
                ),
            )

            final_mastery = min(
                self.config.mastery_gain_cap,
                current_mastery + gain,
            )

            per_kp_gains.append(gain)
            per_kp_final.append(final_mastery)

        # 平均最终掌握度
        avg_final_mastery = (
            sum(per_kp_final) / len(per_kp_final)
            if per_kp_final else 0.0
        )

        # 加权总分
        score = (
            self.config.coverage_weight * coverage
            + self.config.mastery_weight * avg_final_mastery
        )

        return LearningEffectDetail(
            coverage=float(coverage),
            avg_final_mastery=float(avg_final_mastery),
            per_kp_gains=per_kp_gains,
            per_kp_final_mastery=per_kp_final,
            score=float(score),
        )

    def _compute_kp_learning_gain(
        self,
        kp: KnowledgePointMeta,
        rank: int,
        total_ranks: int,
        learned_ids: set,
    ) -> float:
        """计算单个知识点的学习增益

        增益 = base_gain × position_factor × prerequisites_bonus × difficulty_adjust × learning_speed

        其中:
          position_factor:
            - 学习顺序靠前 → 有更多后续练习时间 → 增益大
            - 但太靠前 → 前置知识不足 → 增益受限
            - 使用: 1.0 - forgetting_factor ^ normalized_rank
          prerequisites_bonus:
            - 所有前置依赖已学完 → bonus = 1.0
            - 部分前置未学 → bonus 衰减 = learned_prereqs / total_prereqs
          difficulty_adjust:
            - 高难度知识点需要更长时间 → 增益系数调整
            - difficulty_normalized ∈ [0, 1] → 1 + 0.2 × (1 - difficulty_normalized)
          learning_speed:
            - 学生个性化学习速度系数
        """
        base_gain = self.config.base_learning_gain
        forgetting = self.config.forgetting_factor

        # ---- 位置因子 (遗忘曲线) ----
        # 遗忘因子越大 → 遗忘越慢 → 保留率越高
        # 位置越靠后 (normalized_rank 越大) → 刚学完, 保留更多
        # 位置越靠前 → 学完后时间间隔长, 但有回顾巩固效应
        # 使用 U 形曲线: 最早和最新学的都有较好保留度
        normalized_rank = rank / max(total_ranks - 1, 1)  # [0, 1]
        # 最近学效应 (recency): 越靠后越新鲜, 保留更多
        recency_factor = forgetting ** normalized_rank
        # 首因效应 (primacy): 越靠前越早学, 有更多巩固时间
        primacy_factor = forgetting ** (1.0 - normalized_rank)
        # 综合位置因子 (取最大值)
        position_factor = max(recency_factor, primacy_factor * 0.8)

        # ---- 前置依赖奖励 ----
        prereq_ids = set(kp.prerequisites)
        if len(prereq_ids) == 0:
            prereq_bonus = 1.0
        else:
            learned_prereqs = len(prereq_ids & learned_ids)
            prereq_bonus = learned_prereqs / len(prereq_ids)

        # ---- 难度调整 ----
        # 难度高 → 基础增益略低 → 需要更多学习时间
        difficulty_normalized = min(kp.difficulty / 5.0, 1.0)
        # 高难度知识点需要更长时间消化, 此处用 (1 - 0.15×normalized)
        difficulty_adjust = 1.0 - 0.15 * difficulty_normalized

        # ---- 重点关注加成 ----
        focus_bonus = 1.5 if kp.id in self.student.focus_areas else 1.0

        # ---- 综合增益 ----
        gain = (
            base_gain
            * position_factor
            * prereq_bonus
            * difficulty_adjust
            * self.student.learning_speed
            * focus_bonus
        )

        # 边界裁剪
        gain = max(0.0, min(gain, 1.0))

        return gain

    # ============================================================
    # Step 4: 认知负荷评估
    #
    # 认知负荷得分 = avg_daily_load / threshold + difficulty_density × w_density
    #
    # 其中:
    #   avg_daily_load:  平均每日学习时长 (小时)
    #   threshold:       单日学习量阈值 (默认 3 小时)
    #   difficulty_density: 相邻高难度知识点的密集度
    #   w_density:       密集度权重 (默认 0.3)
    # ============================================================

    def _calculate_daily_load(self, order: List[int]) -> List[float]:
        """估算每日学习负荷 (小时)

        将学习路径按天分组:
          - 默认总天数 = max(7, ceil(总知识点数 / 每日合理量))
          - 每天的知识点数基本相同
          - 返回每天预估学习时长列表
        """
        if not self.kps:
            return []

        total_kps = len(order)
        # 动态计算总天数: 基于总学习时长和每日最大时长。
        # 分组上限统一采用学生真实 max_daily_hours (而非独立的
        # daily_load_threshold_hours 软阈值), 避免阈值 < 上限导致的
        # "每天都超负荷" 退化解 (AOOConfig 两参数语义统一)。
        daily_cap = max(self.student.max_daily_hours, 0.01)
        total_hours = sum(kp.estimated_hours for kp in self.kps)
        suggested_days = max(
            1,
            int(np.ceil(total_hours / daily_cap)),
            int(np.ceil(total_kps / 5)),  # 每天最多 5 个知识点
        )
        # 限制最小天数 (至少 3 天) 和最大天数
        num_days = max(3, min(suggested_days, 14))

        kps_per_day = max(1, int(np.ceil(total_kps / num_days)))

        daily_load = []
        for day in range(num_days):
            start = day * kps_per_day
            end = min(start + kps_per_day, total_kps)
            day_hours = 0.0
            for i in range(start, end):
                kp_idx = order[i]
                if kp_idx < len(self.kps):
                    day_hours += self.kps[kp_idx].estimated_hours
            daily_load.append(day_hours)

        return daily_load

    def _calculate_cognitive_load_detail(
        self, daily_load: List[float], order: List[int]
    ) -> CognitiveLoadDetail:
        """计算认知负荷详细分解

        Returns:
            CognitiveLoadDetail 包含 avg/max daily_load, overload_ratio,
            difficulty_density_score, 综合得分
        """
        n_days = max(len(daily_load), 1)
        threshold = max(self.config.daily_load_threshold_hours, 0.01)

        # ---- 1. 单日学习量统计 ----
        avg_load = sum(daily_load) / n_days
        max_load = max(daily_load) if daily_load else 0.0

        # 超负荷天数占比
        overload_days = sum(1 for h in daily_load if h > threshold)
        overload_ratio = overload_days / n_days

        # ---- 2. 难度密集度 ----
        difficulty_density = self._calculate_difficulty_density(daily_load, order)

        # ---- 3. 综合认知负荷得分 ----
        # 单日负荷分 = avg_daily_load / threshold
        daily_load_score = avg_load / threshold
        # 总得分 = 单日负荷分 + 难度密集度 × 权重
        total_score = (
            daily_load_score
            + self.config.difficulty_density_weight * difficulty_density
        )

        return CognitiveLoadDetail(
            avg_daily_load_hours=float(avg_load),
            max_daily_load_hours=float(max_load),
            overload_ratio=float(overload_ratio),
            difficulty_density_score=float(difficulty_density),
            score=float(total_score),
        )

    def _calculate_difficulty_density(
        self, daily_load: List[float], order: List[int]
    ) -> float:
        """计算知识点难度密集度

        两种惩罚:
          1. 连续高难度: 每天内连续 >=4 级知识点超过 2 个 → 指数惩罚
          2. 全局难度方差: 每天难度不均 → 惩罚不均匀分布
        """
        n_days = max(len(daily_load), 1)
        total_kps = len(order)
        kps_per_day = max(1, int(np.ceil(total_kps / n_days)))

        density_sum = 0.0
        all_day_difficulties: List[List[float]] = []

        for day in range(n_days):
            start = day * kps_per_day
            end = min(start + kps_per_day, total_kps)

            day_diffs: List[float] = []
            for i in range(start, end):
                kp_idx = order[i]
                if kp_idx < len(self.kps):
                    day_diffs.append(self.kps[kp_idx].difficulty)

            all_day_difficulties.append(day_diffs)

            # ---- 连续高难度惩罚 ----
            high_thresh = self.config.high_difficulty_threshold
            consecutive_high = 0
            for d in day_diffs:
                if d >= high_thresh:
                    consecutive_high += 1
                else:
                    if consecutive_high >= 2:
                        # 指数惩罚: consecutive_high 越大惩罚越重
                        density_sum += consecutive_high**1.5 * self.config.consecutive_high_difficulty_penalty
                    consecutive_high = 0

            # 尾部检查
            if consecutive_high >= 2:
                density_sum += consecutive_high**1.5 * self.config.consecutive_high_difficulty_penalty

        # ---- 全局难度均匀性 (变异系数惩罚) ----
        day_avg_diffs = [
            np.mean(diffs) if diffs else 0.0
            for diffs in all_day_difficulties
        ]
        if len(day_avg_diffs) >= 2:
            global_mean = np.mean(day_avg_diffs)
            if global_mean > 0:
                cv = np.std(day_avg_diffs) / global_mean  # 变异系数
                # 不均匀分布 → 额外惩罚
                density_sum += cv * 0.5

        return density_sum

    # ============================================================
    # Step 5: 硬约束 — 前置依赖检查
    # ============================================================

    def _check_prerequisites(self, order: List[int]) -> int:
        """检查前置依赖是否满足 (硬约束)

        遍历学习顺序, 对每个知识点检查其所有前置依赖是否已在之前学过。

        返回: 违反次数 (0 = 完全满足)
        """
        learned = set()
        violations = 0

        for kp_idx in order:
            if kp_idx >= len(self.kps):
                continue
            kp = self.kps[kp_idx]

            for prereq_id in kp.prerequisites:
                if prereq_id in self.kp_index:
                    prereq_idx = self.kp_index[prereq_id]
                    if prereq_idx not in learned:
                        violations += 1
                        logger.debug(
                            "  前置依赖违反: %s (需要 %s, 尚未学习)",
                            kp.id, prereq_id,
                        )

            learned.add(kp_idx)

        return violations

    # ============================================================
    # Pareto 前沿算法
    # ============================================================

    @staticmethod
    def _non_dominated_sort(
        obj1: np.ndarray,   # 目标1: learning_effect (越大越好)
        obj2: np.ndarray,   # 目标2: -cognitive_load_score (越大越好)
    ) -> np.ndarray:
        """非支配排序: 找出 Pareto 前沿

        A dominates B 当且仅当:
          obj1(A) >= obj1(B) AND obj2(A) >= obj2(B)
          AND (obj1(A) > obj1(B) OR obj2(A) > obj2(B))

        返回: boolean mask, True 表示在 Pareto 前沿上
        """
        n = len(obj1)
        is_non_dominated = np.ones(n, dtype=bool)

        for i in range(n):
            if not is_non_dominated[i]:
                continue
            for j in range(n):
                if i == j:
                    continue
                # 检查 j 是否支配 i
                if (
                    obj1[j] >= obj1[i]
                    and obj2[j] >= obj2[i]
                    and (obj1[j] > obj1[i] or obj2[j] > obj2[i])
                ):
                    is_non_dominated[i] = False
                    break

        return is_non_dominated

    def _classify_pareto_paths(self, pf: ParetoFront) -> ParetoFront:
        """从 Pareto 前沿中分类 3 条代表性路径

        分类策略:
          - 效率型: learning_effect 最高 (追求最优学习效果)
          - 稳健型: cognitive_load_score 最低 (控制认知负荷)
          - 平衡型: 最接近理想点 (max_learning_effect, min_cognitive_load)

        理想点: (max_learning_effect, min_cognitive_load_score)
        使用归一化欧氏距离找最优点。

        如果 efficiency_idx == robust_idx (单一解在两端都是最优),
        则设置平衡型为另一个不同解, 效率型和稳健型指向同一解。
        """
        if not pf.fitness_results:
            return pf

        learning = np.array([r.learning_effect for r in pf.fitness_results])
        cognitive = np.array([r.cognitive_load_score for r in pf.fitness_results])

        # ---- 效率型: learning_effect 最高 ----
        pf.efficiency_idx = int(np.argmax(learning))
        pf.fitness_results[pf.efficiency_idx].path_type = "efficiency"

        # ---- 稳健型: cognitive_load_score 最低 ----
        pf.robust_idx = int(np.argmin(cognitive))
        pf.fitness_results[pf.robust_idx].path_type = "robust"

        # ---- 平衡型: 最接近理想点 ----
        if pf.size >= 2:
            # 归一化到 [0, 1]
            l_range = learning.max() - learning.min()
            c_range = cognitive.max() - cognitive.min()
            if l_range < 1e-10 or c_range < 1e-10:
                # 所有解几乎相同, 选第一个不等于效率型的
                for i in range(pf.size):
                    if i != pf.efficiency_idx:
                        pf.balanced_idx = i
                        break
            else:
                learning_norm = (learning - learning.min()) / (l_range + 1e-10)
                cognitive_norm = (cognitive - cognitive.min()) / (c_range + 1e-10)

                # 理想点: (1, 0) — learning 最高, cognitive 最低
                ideal = np.array([1.0, 0.0])
                distances = np.sqrt(
                    (learning_norm - ideal[0]) ** 2
                    + (cognitive_norm - ideal[1]) ** 2
                )

                # 排除已经是 efficiency 或 robust 的索引
                candidates = [i for i in range(pf.size)
                              if i != pf.efficiency_idx and i != pf.robust_idx]
                if candidates:
                    pf.balanced_idx = candidates[int(np.argmin(distances[candidates]))]
                else:
                    # efficiency == robust, 选距离第二小的
                    sorted_order = np.argsort(distances)
                    pf.balanced_idx = int(sorted_order[1]) if len(sorted_order) > 1 else 0
        else:
            pf.balanced_idx = 0

        if 0 <= pf.balanced_idx < len(pf.fitness_results):
            pf.fitness_results[pf.balanced_idx].path_type = "balanced"

        return pf


# ============================================================
# 工厂函数: 从诊断数据构建 FitnessCalculator
# ============================================================


def build_fitness_calculator(
    knowledge_points: List[dict],
    student_mastery: Dict[str, float],
    focus_areas: Optional[List[str]] = None,
    max_daily_hours: float = 4.0,
    learning_speed: float = 1.0,
    config: Optional[AOOConfig] = None,
) -> FitnessCalculator:
    """从诊断数据构建适应度计算器

    Args:
        knowledge_points: 知识点列表, 每项格式:
            {id, name, difficulty, layer, prerequisites (list of id), estimated_hours}
        student_mastery: 学生掌握度字典 {kp_id: mastery [0, 1]}
        focus_areas: 重点关注知识点 id 列表
        max_daily_hours: 每日最大学习时长
        learning_speed: 学习速度系数
        config: AOO 配置 (默认使用全局实例)
    """
    kps = []
    for kp_data in knowledge_points:
        kp = KnowledgePointMeta(
            id=str(kp_data.get("id", "")),
            name=str(kp_data.get("name", "")),
            difficulty=float(kp_data.get("difficulty", 1.0)),
            layer=str(kp_data.get("layer", "core")),
            prerequisites=[str(p) for p in kp_data.get("prerequisites", [])],
            estimated_hours=float(kp_data.get("estimated_hours", 1.0)),
        )
        kps.append(kp)

    profile = StudentProfile(
        current_mastery=dict(student_mastery),
        max_daily_hours=max_daily_hours,
        learning_speed=learning_speed,
        focus_areas=focus_areas or [],
    )

    return FitnessCalculator(
        knowledge_points=kps,
        student_profile=profile,
        config=config,
    )
