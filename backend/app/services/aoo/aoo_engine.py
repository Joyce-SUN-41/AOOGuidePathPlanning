"""AOO (Animated Oat Optimization) 核心算法引擎

论文: 《The Animated Oat Optimization Algorithm》

算法灵感来源于燕麦种子的传播策略，模拟燕麦种子通过风、水、动物
传播（探索阶段），以及湿敏滚动和遇障碍弹射（开发阶段）的优化过程。

核心公式索引：
  初始化:  公式 1-2   (随机种群生成)
  参数计算: 公式 3     (m, L, e, c 参数)
  探索阶段: 公式 4-5   (风/水/动物传播)
  开发-滚动: 公式 6-10  (Lévy 飞行 + 滚动)
  开发-弹射: 公式 11-14 (抛体运动 + Lévy 飞行)

使用方式:
    engine = AOOEngine(config, fitness_calculator)
    result = engine.optimize()
"""

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from app.services.aoo.aoo_config import AOOConfig, default_config
from app.services.aoo.fitness_calculator import FitnessCalculator, FitnessResult

logger = logging.getLogger(__name__)


# ============================================================
# 类型定义
# ============================================================


@dataclass
class PopulationSnapshot:
    """单代种群快照 — 对应前端 PopulationSnapshot schema"""

    iteration: int
    fitness_values: List[float]
    best_index: int
    positions_x: List[float] = field(default_factory=list)
    positions_y: List[float] = field(default_factory=list)
    colors: List[str] = field(default_factory=list)


@dataclass
class ConvergenceData:
    """收敛曲线完整数据"""

    iterations: List[int] = field(default_factory=list)
    best_fitness: List[float] = field(default_factory=list)
    avg_fitness: List[float] = field(default_factory=list)
    diversity: List[float] = field(default_factory=list)
    median_fitness: List[float] = field(default_factory=list)
    q1_fitness: List[float] = field(default_factory=list)
    q3_fitness: List[float] = field(default_factory=list)
    snapshots: List[PopulationSnapshot] = field(default_factory=list)


@dataclass
class OptimizationResult:
    """优化器最终输出"""

    best_position: np.ndarray               # 最优个体位置
    best_fitness: float                      # 最优适应度
    convergence: ConvergenceData             # 收敛曲线数据
    total_iterations: int                    # 实际迭代次数
    total_time_seconds: float                # 总耗时
    final_population: np.ndarray             # 最终种群 (可选)
    log_entries: List[Dict[str, Any]] = field(default_factory=list)  # 寻优日志


# ============================================================
# AOO 算法核心类
# ============================================================


class AOOEngine:
    """燕麦动画优化算法 (Animated Oat Optimization) 核心引擎

    实现论文中完整的优化流程：
      1. 随机初始化种群 (公式 1-2)
      2. 计算动态参数 (公式 3)
      3. 探索阶段 — 风/水/动物传播 (公式 4-5)
      4. 开发阶段 — 湿敏滚动 (公式 6-10)
      5. 开发阶段 — 遇障碍弹射 (公式 11-14)
      6. 边界约束 & 精英保留
    """

    def __init__(
        self,
        config: Optional[AOOConfig] = None,
        fitness_calculator: Optional[FitnessCalculator] = None,
    ):
        self.config = config or default_config
        self.fitness_calc = fitness_calculator

        # 设置随机种子
        self._rng = np.random.RandomState(self.config.seed)

        # 运行时状态
        self._population: Optional[np.ndarray] = None
        self._fitness: Optional[np.ndarray] = None
        self._best_position: Optional[np.ndarray] = None
        self._best_fitness: float = -np.inf
        self._best_fitness_history: List[float] = []
        # 本代中处于"探索态"的个体下标 (探索阶段传播 / 弹射跳跃)
        # 仅用于可视化着色, 不参与任何寻优计算
        self._exploring_indices: set = set()

        # 预计算 Lévy 飞行参数
        self._levy_sigma_u = self._compute_levy_sigma_u()

    # ============================================================
    # 公共接口
    # ============================================================

    def optimize(
        self,
        on_iteration: Optional[callable] = None,
    ) -> OptimizationResult:
        """执行 AOO 优化主循环

        Args:
            on_iteration: 每代回调 callable(iteration, best_fitness, avg_fitness, diversity)
                          用于实时上报收敛数据，例如写入 Redis 供前端轮询

        Returns:
            OptimizationResult 包含最优解和完整收敛数据
        """
        t_start = time.perf_counter()
        logger.info(
            "AOO optimization started | N=%d Dim=%d T_max=%d seed=%d",
            self.config.population_size,
            self.config.dim,
            self.config.max_iterations,
            self.config.seed,
        )

        conv = ConvergenceData()
        log_entries: List[Dict[str, Any]] = []
        stagnation_counter = 0

        # ---- Phase 1: 初始化 (公式 1-2) ----
        self._initialize_population()

        # ---- 初始评估 (初始化适应度) ----
        N = self.config.population_size
        self._fitness = np.zeros(N)
        for i in range(N):
            fr = self.fitness_calc.evaluate(self._population[i])
            self._fitness[i] = fr.total_fitness
        best_idx = int(np.argmax(self._fitness))
        self._best_fitness = float(self._fitness[best_idx])
        self._best_position = self._population[best_idx].copy()

        for t in range(1, self.config.max_iterations + 1):
            # ---- 参数计算 (公式 3) ----
            params = self._calculate_parameters(t)

            # 每代开始清空探索态标记 (仅可视化用)
            self._exploring_indices = set()

            # ---- Phase 2: 探索阶段 (公式 4-5) ----
            if self._rng.random() < self._get_exploration_rate(t):
                self._exploration_phase(params)

            # ---- Phase 3: 开发阶段 — 滚动 (公式 6-10) ----
            self._exploitation_rolling(params)

            # ---- Phase 4: 开发阶段 — 弹射 (公式 11-14) ----
            self._exploitation_ejection(params)

            # ---- 边界约束 ----
            self._apply_bounds()

            # ---- 评估 & 精英保留 ----
            self._evaluate_and_elitism()

            # ---- 记录收敛数据 ----
            self._record_convergence(t, conv)

            # ---- 每代回调 (实时收敛上报) ----
            if on_iteration is not None:
                try:
                    on_iteration(
                        t,
                        float(self._best_fitness),
                        float(np.mean(self._fitness)),
                        float(self._calculate_diversity()),
                    )
                except Exception as cb_exc:
                    logger.warning("iteration callback failed at iter=%d: %s", t, cb_exc)

            # ---- 种群快照 ----
            if t % self.config.snapshot_interval == 0 and len(conv.snapshots) < self.config.max_snapshots:
                conv.snapshots.append(self._capture_snapshot(t))

            # ---- 寻优日志 ----
            entry = self._make_log_entry(t, params)
            log_entries.append(entry)

            if t % 50 == 0 or t == 1:
                logger.info(
                    "iter=%4d | best_f=%.6f avg_f=%.6f diversity=%.4f c=%.4f",
                    t, conv.best_fitness[-1], conv.avg_fitness[-1],
                    conv.diversity[-1], params["c"],
                )

            # ---- 更新停滞计数 (先于早停判断, 避免一代延迟) ----
            if t > 1 and abs(conv.best_fitness[-1] - conv.best_fitness[-2]) < self.config.early_stop_tolerance:
                stagnation_counter += 1
            else:
                stagnation_counter = 0

            # ---- 早停检查 (使用本轮已更新的停滞计数) ----
            if self._check_early_stop(conv, stagnation_counter):
                logger.info("Early stop triggered at iteration %d", t)
                break

        t_elapsed = time.perf_counter() - t_start
        logger.info(
            "AOO optimization finished | iter=%d time=%.2fs best_f=%.6f",
            len(conv.iterations), t_elapsed, self._best_fitness,
        )

        return OptimizationResult(
            best_position=self._best_position.copy(),
            best_fitness=float(self._best_fitness),
            convergence=conv,
            total_iterations=len(conv.iterations),
            total_time_seconds=t_elapsed,
            final_population=self._population.copy(),
            log_entries=log_entries,
        )

    # ============================================================
    # Phase 1: 初始化 (公式 1-2)
    # ============================================================

    def _initialize_population(self) -> None:
        """公式 1-2: 随机初始化种群

        X_i = LB + r_i ⊗ (UB - LB),  i = 1, 2, ..., N

        其中 r_i ~ U(0, 1) 是 Dim 维随机向量，⊗ 是逐元素乘法。
        """
        lb, ub = self.config.lb, self.config.ub
        N, Dim = self.config.population_size, self.config.dim

        self._population = lb + self._rng.rand(N, Dim) * (ub - lb)
        self._best_fitness = -np.inf
        self._best_position = None

        logger.debug(
            "Population initialized: shape=(%d,%d) range=[%.2f, %.2f]",
            N, Dim, lb, ub,
        )

    # ============================================================
    # Phase 2: 参数计算 (公式 3)
    # ============================================================

    def _calculate_parameters(self, t: int) -> Dict[str, float]:
        """公式 3: 计算每轮迭代的动态参数

        m = 0.5 * (r / Dim)           # 质量 (mass)
        L = N * (r / Dim)             # 芒长 (awn length)
        e = 0.5 * (r / Dim)           # 偏心系数 (eccentricity)
        c = 1 - (t / T_max)³          # 动态调整因子

        其中 r ~ U(0, 1) 为每轮生成的随机数。
        """
        r = self._rng.random()
        Dim = self.config.dim
        N = self.config.population_size
        T_max = self.config.max_iterations

        m = 0.5 * (r / Dim)
        L = N * (r / Dim)
        e = 0.5 * (r / Dim)
        c = 1.0 - (t / T_max) ** 3

        return {"m": m, "L": L, "e": e, "c": c, "r": r}

    # 兼容命名：部分调用方按公开方法名调用
    def calculate_parameters(self, t: int) -> Dict[str, float]:
        return self._calculate_parameters(t)

    # ============================================================
    # Phase 3: 探索阶段 (公式 4-5)
    # ============================================================

    def _exploration_phase(self, params: Dict[str, float]) -> None:
        """公式 4-5: 探索阶段 — 风/水/动物传播

        将种群均分为三组:
          Group 1 (top 1/3)    — 风传播: X_new = X + W
          Group 2 (middle 1/3) — 水传播: X_new = X + m*L*(X_r1 - X_r2)
          Group 3 (bottom 1/3) — 动物传播: X_new = X + e*c*(X_best - X)

        其中 W = (c/π) * (2*r_Dim - 1) ⊗ UB
        """
        N = self.config.population_size
        Dim = self.config.dim
        c = params["c"]
        m = params["m"]
        L_val = params["L"]
        e = params["e"]

        # 按适应度排序
        sorted_indices = np.argsort(self._fitness)[::-1]
        third = N // 3

        new_pop = self._population.copy()

        # ---- Group 1: 风传播 (最佳 1/3) ----
        # W = (c/π) * (2*r_Dim - 1) ⊗ UB
        group1 = sorted_indices[:third]
        if len(group1) > 0:
            W = (c / np.pi) * (2 * self._rng.rand(len(group1), Dim) - 1) * self.config.ub
            new_pop[group1] = self._population[group1] + W

        # ---- Group 2: 水传播 (中间 1/3) ----
        group2 = sorted_indices[third : 2 * third]
        if len(group2) > 0:
            for i in group2:
                r1, r2 = self._rng.choice(N, size=2, replace=False)
                new_pop[i] = self._population[i] + m * L_val * (self._population[r1] - self._population[r2])

        # ---- Group 3: 动物传播 (最差 1/3) ----
        group3 = sorted_indices[2 * third :]
        if len(group3) > 0:
            for i in group3:
                new_pop[i] = self._population[i] + e * c * (self._best_position - self._population[i])

        self._population = new_pop

        # 标记本代经历"远距离传播"的个体 (风/水传播) 为探索态
        # Group 3 (动物传播) 是朝最优解收敛, 不算探索, 故不标记
        # 仅用于可视化着色, 不影响算法
        self._exploring_indices.update(int(i) for i in group1)
        self._exploring_indices.update(int(i) for i in group2)

    def explore_phase(self, params: Dict[str, float]) -> None:
        self._exploration_phase(params)

    # ============================================================
    # Phase 4: 开发阶段 — 滚动 (公式 6-10)
    # ============================================================

    def _exploitation_rolling(self, params: Dict[str, float]) -> None:
        """公式 6-10: 开发阶段 — 湿敏滚动运动

        对适应度高于平均值的个体:
          R = m * L * (X_r1 - X_r2)
          X_new(i) = X_best + R + c * Levy(Dim) ⊗ X_best

        Lévy 飞行 (公式 8-9, β = 1.5):
          Levy(Dim) = σ * u / |v|^(1/β)
          u ~ N(0, σ_u²), v ~ N(0, 1)
        """
        N = self.config.population_size
        Dim = self.config.dim
        c = params["c"]
        m = params["m"]
        L_val = params["L"]

        avg_fitness = np.mean(self._fitness)
        above_avg = np.where(self._fitness >= avg_fitness)[0]

        if len(above_avg) == 0:
            return

        levy_vec = self._levy_flight(len(above_avg), Dim)

        new_pop = self._population.copy()
        for idx, i in enumerate(above_avg):
            r1, r2 = self._rng.choice(N, size=2, replace=False)
            R = m * L_val * (self._population[r1] - self._population[r2])
            new_pop[i] = self._best_position + R + c * levy_vec[idx] * self._best_position

        self._population = new_pop

    def exploit_phase_rolling(self, params: Dict[str, float]) -> None:
        self._exploitation_rolling(params)

    # ============================================================
    # Phase 5: 开发阶段 — 弹射 (公式 11-14)
    # ============================================================

    def _exploitation_ejection(self, params: Dict[str, float]) -> None:
        """公式 11-14: 开发阶段 — 遇障碍储能弹射

        对适应度低于平均值的个体:
          J = e * (X_best - X(i))
          X_new(i) = X_best + J + c * Levy(Dim) ⊗ X_best

        模拟燕麦种子遇到障碍物后储能弹射的抛体运动。
        """
        N = self.config.population_size
        Dim = self.config.dim
        c = params["c"]
        e = params["e"]

        avg_fitness = np.mean(self._fitness)
        below_avg = np.where(self._fitness < avg_fitness)[0]

        if len(below_avg) == 0:
            return

        levy_vec = self._levy_flight(len(below_avg), Dim)

        new_pop = self._population.copy()
        for idx, i in enumerate(below_avg):
            J = e * (self._best_position - self._population[i])
            new_pop[i] = self._best_position + J + c * levy_vec[idx] * self._best_position

        self._population = new_pop

        # 弹射跳跃个体同样标记为探索态 (可视化着色用, 不影响算法)
        self._exploring_indices.update(int(i) for i in below_avg)

    def exploit_phase_eject(self, params: Dict[str, float]) -> None:
        self._exploitation_ejection(params)

    # ============================================================
    # 边界约束 & 评估
    # ============================================================

    def _apply_bounds(self) -> None:
        """将种群值限制在 [LB, UB] 范围内"""
        np.clip(
            self._population,
            self.config.lb,
            self.config.ub,
            out=self._population,
        )

    def _evaluate_and_elitism(self) -> None:
        """评估种群适应度并执行精英保留"""
        N = self.config.population_size

        # 评估所有个体
        new_fitness = np.zeros(N)
        for i in range(N):
            result = self.fitness_calc.evaluate(self._population[i])
            new_fitness[i] = result.total_fitness

        # 精英保留: 如果历史最优比当前代最优更好, 替换最差个体
        if self._best_position is not None:
            worst_idx = np.argmin(new_fitness)
            if self._best_fitness > new_fitness[worst_idx]:
                self._population[worst_idx] = self._best_position.copy()
                new_fitness[worst_idx] = self._best_fitness

        self._fitness = new_fitness

        # 更新全局最优
        current_best_idx = np.argmax(self._fitness)
        if self._fitness[current_best_idx] > self._best_fitness:
            self._best_fitness = float(self._fitness[current_best_idx])
            self._best_position = self._population[current_best_idx].copy()

    # ============================================================
    # 收敛记录 & 快照
    # ============================================================

    def _record_convergence(self, t: int, conv: ConvergenceData) -> None:
        """记录每代收敛指标"""
        conv.iterations.append(t)
        conv.best_fitness.append(float(self._best_fitness))
        conv.avg_fitness.append(float(np.mean(self._fitness)))
        conv.diversity.append(float(self._calculate_diversity()))
        conv.median_fitness.append(float(np.median(self._fitness)))

        # 四分位数
        sorted_f = np.sort(self._fitness)
        conv.q1_fitness.append(float(np.percentile(sorted_f, 25)))
        conv.q3_fitness.append(float(np.percentile(sorted_f, 75)))

    def _capture_snapshot(self, iteration: int) -> PopulationSnapshot:
        """捕获当前代种群快照

        将高维种群降维到 2D 平面 (取前两维) 用于前端散点动画，
        并根据个体状态着色: elite (最优个体) / exploring (探索阶段高探索率时) / normal。
        """
        pop = self._population  # (N, Dim)
        N = pop.shape[0]
        Dim = pop.shape[1]

        # 降维: 优先使用前两维；维度不足时用随机微扰散布避免重叠
        if Dim >= 2:
            positions_x = pop[:, 0].tolist()
            positions_y = pop[:, 1].tolist()
        elif Dim == 1:
            positions_x = pop[:, 0].tolist()
            positions_y = (self._rng.rand(N) - 0.5).tolist()
        else:
            positions_x = (self._rng.rand(N) - 0.5).tolist()
            positions_y = (self._rng.rand(N) - 0.5).tolist()

        best_idx = int(np.argmax(self._fitness))
        # 三态着色: elite (当代最优) > exploring (本代刚经历远距离传播/弹射跳跃) > normal
        colors = []
        for i in range(N):
            if i == best_idx:
                colors.append("elite")
            elif i in self._exploring_indices:
                colors.append("exploring")
            else:
                colors.append("normal")

        return PopulationSnapshot(
            iteration=iteration,
            fitness_values=self._fitness.tolist(),
            best_index=best_idx,
            positions_x=[float(v) for v in positions_x],
            positions_y=[float(v) for v in positions_y],
            colors=colors,
        )

    def _make_log_entry(self, t: int, params: Dict[str, float]) -> Dict[str, Any]:
        """生成单轮寻优日志条目"""
        return {
            "iteration": t,
            "best_fitness": float(self._best_fitness),
            "avg_fitness": float(np.mean(self._fitness)),
            "worst_fitness": float(np.min(self._fitness)),
            "diversity": float(self._calculate_diversity()),
            "params": {k: round(v, 6) for k, v in params.items()},
        }

    # ============================================================
    # Lévy 飞行 (公式 8-9)
    # ============================================================

    def _compute_levy_sigma_u(self) -> float:
        """计算 Lévy 飞行中 σ_u 参数

        σ_u = [Γ(1+β) * sin(πβ/2) / (Γ((1+β)/2) * β * 2^((β-1)/2))]^(1/β)
        """
        beta = self.config.levy_beta
        num = math.gamma(1 + beta) * np.sin(np.pi * beta / 2)
        den = math.gamma((1 + beta) / 2) * beta * 2 ** ((beta - 1) / 2)
        return (num / den) ** (1 / beta)

    def _levy_flight(self, n: int, dim: int) -> np.ndarray:
        """公式 8-9: 生成 Lévy 飞行步长

        Levy(Dim) = σ * u / |v|^(1/β)

        其中:
          u ~ N(0, σ_u²)
          v ~ N(0, 1)
          β = 1.5

        Returns:
            np.ndarray shape=(n, dim)
        """
        beta = self.config.levy_beta
        sigma = self.config.levy_sigma

        # 标准正态分布采样
        u = self._rng.normal(0, self._levy_sigma_u, size=(n, dim))
        v = self._rng.normal(0, 1, size=(n, dim))

        # Lévy 步长
        levy = sigma * u / (np.abs(v) ** (1.0 / beta) + 1e-15)

        return levy

    # ============================================================
    # 辅助方法
    # ============================================================

    def _get_exploration_rate(self, t: int) -> float:
        """计算当前迭代的探索概率

        使用余弦退火策略: 前期高探索, 后期低探索。
        """
        T_max = self.config.max_iterations
        base_rate = self.config.exploration_rate
        # 余弦退火: 从 base_rate 逐渐降低到 0.05
        rate = 0.05 + (base_rate - 0.05) * (0.5 * (1 + np.cos(np.pi * t / T_max)))
        return float(rate)

    def _calculate_diversity(self) -> float:
        """计算种群多样性

        diversity = (1/N) * Σ_i ||X_i - X_centroid|| / ||UB - LB||

        值域 [0, 1], 值越大表示种群越分散。
        """
        centroid = np.mean(self._population, axis=0)
        distances = np.linalg.norm(self._population - centroid, axis=1)
        max_dist = np.linalg.norm(
            np.full(self.config.dim, self.config.ub)
            - np.full(self.config.dim, self.config.lb)
        )
        if max_dist == 0:
            return 0.0
        diversity = np.mean(distances) / max_dist
        return float(np.clip(diversity, 0.0, 1.0))

    def _check_early_stop(
        self, conv: ConvergenceData, stagnation_counter: int
    ) -> bool:
        """检查是否应早停"""
        patience = self.config.early_stop_patience
        if stagnation_counter < patience:
            return False
        # 确认多样性也足够低 (种群已收敛)
        recent_diversity = conv.diversity[-patience:] if len(conv.diversity) >= patience else conv.diversity
        if np.mean(recent_diversity) < 0.01:
            return True
        return False

    def _populate_dummy_convergence(
        self, n_iterations: int, constant_fitness: float
    ) -> ConvergenceData:
        """生成虚拟收敛数据 (用于测试早停)

        Args:
            n_iterations: 虚拟迭代次数
            constant_fitness: 恒定的适应度值
        """
        conv = ConvergenceData()
        for t in range(1, n_iterations + 1):
            conv.iterations.append(t)
            conv.best_fitness.append(constant_fitness)
            conv.avg_fitness.append(constant_fitness)
            conv.diversity.append(0.001)  # 极低多样性
            conv.median_fitness.append(constant_fitness)
            conv.q1_fitness.append(constant_fitness)
            conv.q3_fitness.append(constant_fitness)
        return conv

    @property
    def population_size_actual(self) -> int:
        """当前实际种群规模"""
        return self._population.shape[0] if self._population is not None else 0


class AOOOptimizer(AOOEngine):
    """历史命名兼容别名。"""

    pass
