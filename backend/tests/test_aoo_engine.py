"""AOO 算法单元测试 (增强版)

验证:
  1. 初始化正确性 (公式 1-2)
  2. 参数计算正确性 (公式 3)
  3. Lévy 飞行生成 (公式 8-9)
  4. 探索阶段正确性 (公式 4-5)
  5. 开发 - 滚动阶段 (公式 6-10)
  6. 开发 - 弹射阶段 (公式 11-14)
  7. 适应度函数: 学习效果 (含遗忘曲线)
  8. 适应度函数: 认知负荷评估
  9. 适应度函数: 硬约束 & 非严格模式
  10. Pareto 前沿提取 & 路径分类
  11. 收敛曲线数据完整性
  12. 配置环境变量覆盖
  13. 早停机制
  14. 随机种子可复现性
  15. 种群多样性计算
  16. 集成测试 (含 Pareto 路径)
"""

import math
import os
from unittest.mock import patch

import numpy as np
import pytest

from app.services.aoo.aoo_config import AOOConfig
from app.services.aoo.aoo_engine import AOOEngine, OptimizationResult
from app.services.aoo.fitness_calculator import (
    CognitiveLoadDetail,
    FitnessCalculator,
    FitnessResult,
    KnowledgePointMeta,
    LearningEffectDetail,
    ParetoFront,
    StudentProfile,
    build_fitness_calculator,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def simple_config() -> AOOConfig:
    """轻量配置 — 用于快速测试"""
    return AOOConfig(
        population_size=10,
        dim=5,
        lb=0.0,
        ub=1.0,
        max_iterations=20,
        early_stop_patience=100,  # 禁用早停
        seed=42,
    )


@pytest.fixture
def sample_kps() -> list:
    """示例知识点数据 (5 个知识点, 含前置依赖链)"""
    return [
        {
            "id": "kp_1",
            "name": "变量与类型",
            "difficulty": 2,
            "layer": "basic",
            "prerequisites": [],
            "estimated_hours": 1.0,
        },
        {
            "id": "kp_2",
            "name": "条件语句",
            "difficulty": 3,
            "layer": "basic",
            "prerequisites": ["kp_1"],
            "estimated_hours": 1.5,
        },
        {
            "id": "kp_3",
            "name": "循环结构",
            "difficulty": 4,
            "layer": "core",
            "prerequisites": ["kp_1", "kp_2"],
            "estimated_hours": 2.0,
        },
        {
            "id": "kp_4",
            "name": "函数定义",
            "difficulty": 3,
            "layer": "core",
            "prerequisites": ["kp_2"],
            "estimated_hours": 1.5,
        },
        {
            "id": "kp_5",
            "name": "递归算法",
            "difficulty": 5,
            "layer": "advanced",
            "prerequisites": ["kp_3", "kp_4"],
            "estimated_hours": 3.0,
        },
    ]


@pytest.fixture
def student_mastery() -> dict:
    """学生当前掌握度"""
    return {
        "kp_1": 0.8,
        "kp_2": 0.5,
        "kp_3": 0.2,
        "kp_4": 0.3,
        "kp_5": 0.0,
    }


@pytest.fixture
def fitness_calc(sample_kps, student_mastery, simple_config) -> FitnessCalculator:
    """标准适应度计算器"""
    return build_fitness_calculator(
        knowledge_points=sample_kps,
        student_mastery=student_mastery,
        config=simple_config,
    )


@pytest.fixture
def engine(simple_config, fitness_calc) -> AOOEngine:
    """标准 AOO 引擎"""
    return AOOEngine(config=simple_config, fitness_calculator=fitness_calc)


# ============================================================
# 测试: 初始化 (公式 1-2)
# ============================================================


class TestInitialization:
    """公式 1-2: 种群初始化"""

    def test_population_shape(self, engine):
        engine._initialize_population()
        assert engine._population.shape == (
            engine.config.population_size,
            engine.config.dim,
        )

    def test_population_bounds(self, engine):
        engine._initialize_population()
        assert np.all(engine._population >= engine.config.lb)
        assert np.all(engine._population <= engine.config.ub)

    def test_population_randomness(self, engine):
        engine._initialize_population()
        pop1 = engine._population.copy()
        engine._initialize_population()
        pop2 = engine._population.copy()
        assert not np.allclose(pop1, pop2)


# ============================================================
# 测试: 参数计算 (公式 3)
# ============================================================


class TestParameterCalculation:
    """公式 3: 动态参数"""

    def test_mass_parameter(self, engine):
        engine._initialize_population()
        for t in range(1, 6):
            params = engine._calculate_parameters(t)
            assert 0 <= params["m"] <= 1

    def test_dynamic_factor_cubic_decay(self, engine):
        T_max = engine.config.max_iterations
        c_values = []
        for t in [1, T_max // 2, T_max]:
            params = engine._calculate_parameters(t)
            c_values.append(params["c"])
        assert c_values[0] > c_values[1] > c_values[2]
        assert c_values[0] > 0.99
        assert c_values[2] < 0.01


# ============================================================
# 测试: Lévy 飞行 (公式 8-9)
# ============================================================


class TestLevyFlight:
    """公式 8-9: Lévy 飞行"""

    def test_levy_shape(self, engine):
        levy = engine._levy_flight(n=10, dim=5)
        assert levy.shape == (10, 5)

    def test_levy_not_zero(self, engine):
        levy = engine._levy_flight(n=100, dim=10)
        assert not np.allclose(levy, 0)

    def test_levy_has_outliers(self, engine):
        levy = engine._levy_flight(n=1000, dim=1)
        std = np.std(levy)
        max_abs = np.max(np.abs(levy))
        assert max_abs > 3 * std

    def test_levy_sigma_u_positive(self, engine):
        assert engine._levy_sigma_u > 0

    def test_levy_seed_reproducibility(self):
        config1 = AOOConfig(seed=123, dim=5, lb=0, ub=1)
        engine1 = AOOEngine(config=config1)
        config2 = AOOConfig(seed=123, dim=5, lb=0, ub=1)
        engine2 = AOOEngine(config=config2)
        levy1 = engine1._levy_flight(10, 5)
        levy2 = engine2._levy_flight(10, 5)
        assert np.allclose(levy1, levy2)


# ============================================================
# 测试: 探索阶段 (公式 4-5)
# ============================================================


class TestExploration:
    """公式 4-5: 探索阶段"""

    def test_exploration_changes_population(self, engine):
        engine._initialize_population()
        engine._fitness = np.random.randn(engine.config.population_size)
        engine._best_position = engine._population[0].copy()
        engine._best_fitness = engine._fitness[0]
        old_pop = engine._population.copy()
        params = engine._calculate_parameters(1)
        engine._exploration_phase(params)
        assert not np.allclose(old_pop, engine._population)

    def test_exploration_within_bounds_after_clip(self, engine):
        engine._initialize_population()
        engine._fitness = np.random.randn(engine.config.population_size)
        engine._best_position = engine._population[0].copy()
        engine._best_fitness = engine._fitness[0]
        params = engine._calculate_parameters(1)
        engine._exploration_phase(params)
        engine._apply_bounds()
        assert np.all(engine._population >= engine.config.lb)
        assert np.all(engine._population <= engine.config.ub)


# ============================================================
# 测试: 开发 — 滚动 (公式 6-10)
# ============================================================


class TestExploitationRolling:
    """公式 6-10: 滚动"""

    def test_rolling_changes_population(self, engine):
        engine._initialize_population()
        N = engine.config.population_size
        engine._fitness = np.ones(N)
        engine._fitness[0] = 100.0
        engine._best_position = engine._population[0].copy()
        engine._best_fitness = 100.0
        old_pop = engine._population.copy()
        params = engine._calculate_parameters(5)
        engine._exploitation_rolling(params)
        assert not np.allclose(old_pop, engine._population)


# ============================================================
# 测试: 开发 — 弹射 (公式 11-14)
# ============================================================


class TestExploitationEjection:
    """公式 11-14: 弹射"""

    def test_ejection_changes_worse_individuals(self, engine):
        engine._initialize_population()
        N = engine.config.population_size
        engine._fitness = np.ones(N)
        engine._fitness[-1] = -100.0
        engine._best_position = engine._population[0].copy()
        engine._best_fitness = 1.0
        old_worst = engine._population[-1].copy()
        params = engine._calculate_parameters(5)
        engine._exploitation_ejection(params)
        engine._apply_bounds()
        assert not np.allclose(old_worst, engine._population[-1])


# ============================================================
# 测试: 适应度 — 学习效果 (增强版, 含遗忘曲线)
# ============================================================


class TestFitnessLearningEffect:
    """学习效果评估 (含遗忘曲线)"""

    def test_fitness_result_structure(self, fitness_calc):
        """适应度结果应包含所有增强字段"""
        pos = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        result = fitness_calc.evaluate(pos)
        assert isinstance(result, FitnessResult)
        assert hasattr(result, "total_fitness")
        assert hasattr(result, "learning_effect")
        assert hasattr(result, "cognitive_load_score")
        assert hasattr(result, "prerequisite_violations")
        assert hasattr(result, "is_feasible")
        assert hasattr(result, "avg_final_mastery")
        assert hasattr(result, "difficulty_density")
        assert hasattr(result, "learning_detail")
        assert hasattr(result, "cognitive_detail")

    def test_coverage_is_one_for_all_kps(self, fitness_calc):
        pos = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        order = fitness_calc._decode_order(pos)
        coverage = fitness_calc._calculate_coverage(order)
        assert coverage == 1.0

    def test_learning_effect_detail_structure(self, fitness_calc):
        """LearningEffectDetail 应包含完整字段"""
        pos = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        order = fitness_calc._decode_order(pos)
        detail = fitness_calc._calculate_learning_effect_detail(order)
        assert isinstance(detail, LearningEffectDetail)
        assert 0 <= detail.coverage <= 1
        assert 0 <= detail.avg_final_mastery <= 1
        assert len(detail.per_kp_gains) == 5
        assert len(detail.per_kp_final_mastery) == 5
        assert detail.score > 0

    def test_learning_effect_score_range(self, fitness_calc):
        """学习效果得分应在合理范围 [0, 1]"""
        pos = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        result = fitness_calc.evaluate(pos)
        assert 0 <= result.learning_effect <= 1.0

    def test_correct_order_yields_feasible(self, fitness_calc):
        """正确顺序 (kp_1→kp_2→kp_3→kp_4→kp_5) 应满足前置依赖"""
        pos_correct = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        result = fitness_calc.evaluate(pos_correct)
        assert result.is_feasible
        assert result.prerequisite_violations == 0

    def test_prerequisite_violation_detected(self, fitness_calc):
        """反向顺序应产生前置依赖违反"""
        pos = np.array([0.5, 0.4, 0.3, 0.2, 0.1])
        result = fitness_calc.evaluate(pos)
        assert result.prerequisite_violations > 0
        assert not result.is_feasible

    def test_correct_order_better_than_reverse(self, fitness_calc):
        """正确顺序适应度应显著优于反向顺序"""
        pos_correct = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        result_correct = fitness_calc.evaluate(pos_correct)
        pos_reverse = np.array([0.5, 0.4, 0.3, 0.2, 0.1])
        result_reverse = fitness_calc.evaluate(pos_reverse)
        assert result_correct.total_fitness > result_reverse.total_fitness

    def test_strict_mode_penalizes_infeasible(self, fitness_calc):
        """严格模式: 不可行解 fitness = -1e9"""
        pos_reverse = np.array([0.5, 0.4, 0.3, 0.2, 0.1])
        result_strict = fitness_calc.evaluate_strict(pos_reverse)
        assert result_strict.total_fitness <= -1e8
        assert not result_strict.is_feasible

    def test_non_strict_mode_gives_gradient(self, fitness_calc):
        """非严格模式: 不可行解有梯度惩罚但非 -∞"""
        pos_reverse = np.array([0.5, 0.4, 0.3, 0.2, 0.1])
        result = fitness_calc.evaluate(pos_reverse, strict=False)
        # 非严格模式有惩罚但不是极大负值
        assert result.total_fitness < 0
        assert result.total_fitness > -1e8

    def test_decode_order_maintains_all_indices(self, fitness_calc):
        pos = np.array([0.3, 0.1, 0.5, 0.2, 0.4])
        order = fitness_calc._decode_order(pos)
        assert set(order) == set(range(5))

    def test_per_kp_gain_positive_for_new_kps(self, fitness_calc):
        """未掌握 (mastery=0) 的知识点应有正向增益"""
        pos = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        order = fitness_calc._decode_order(pos)
        detail = fitness_calc._calculate_learning_effect_detail(order)
        # kp_5 (index 4, mastery=0) 应有正向增益
        kp5_idx_in_order = order.index(4)
        assert detail.per_kp_gains[kp5_idx_in_order] > 0

    def test_forgetting_factor_affects_gain(self, sample_kps, student_mastery):
        """遗忘因子应影响增益大小"""
        cfg_high = AOOConfig(forgetting_factor=0.95)  # 遗忘慢
        cfg_low = AOOConfig(forgetting_factor=0.5)    # 遗忘快

        fc_high = build_fitness_calculator(
            knowledge_points=sample_kps,
            student_mastery=student_mastery,
            config=cfg_high,
        )
        fc_low = build_fitness_calculator(
            knowledge_points=sample_kps,
            student_mastery=student_mastery,
            config=cfg_low,
        )

        pos = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        order = fc_high._decode_order(pos)

        detail_high = fc_high._calculate_learning_effect_detail(order)
        detail_low = fc_low._calculate_learning_effect_detail(order)

        # 遗忘慢 → 增益大 → avg_final_mastery 更高
        assert detail_high.avg_final_mastery >= detail_low.avg_final_mastery


# ============================================================
# 测试: 适应度 — 认知负荷 (增强版)
# ============================================================


class TestFitnessCognitiveLoad:
    """认知负荷评估"""

    def test_cognitive_load_detail_structure(self, fitness_calc):
        """CognitiveLoadDetail 应包含完整字段"""
        pos = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        order = fitness_calc._decode_order(pos)
        daily_load = fitness_calc._calculate_daily_load(order)
        detail = fitness_calc._calculate_cognitive_load_detail(daily_load, order)
        assert isinstance(detail, CognitiveLoadDetail)
        assert detail.avg_daily_load_hours > 0
        assert detail.max_daily_load_hours > 0
        assert detail.score > 0

    def test_daily_load_partition(self, fitness_calc):
        """应合理分天"""
        pos = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        order = fitness_calc._decode_order(pos)
        daily_load = fitness_calc._calculate_daily_load(order)
        assert len(daily_load) >= 1

    def test_cognitive_load_detects_overload(self, student_mastery):
        """超时学习应触发认知负荷 (avg_daily_load > threshold)"""
        # 8 个知识点, 每个 8 小时 → 64h 总时长
        # 64h / 3h_threshold = 22 days, but min(22, 14) = 14 days
        # kps_per_day = ceil(8/14) = 1 → spread over 14 days
        # First 8 days = 8h each, last 6 days = 0
        # avg = 64/14 ≈ 4.57 > 3.0 ✓
        sample_kps_overload = [
            {"id": f"kp_{i}", "name": f"KP{i}", "difficulty": 3,
             "layer": "core", "prerequisites": [], "estimated_hours": 8.0}
            for i in range(8)
        ]
        mastery = {f"kp_{i}": 0.5 for i in range(8)}

        fc = build_fitness_calculator(
            knowledge_points=sample_kps_overload,
            student_mastery=mastery,
            max_daily_hours=4.0,
        )
        pos = np.array([i * 0.12 for i in range(8)])
        order = fc._decode_order(pos)
        daily_load = fc._calculate_daily_load(order)
        detail = fc._calculate_cognitive_load_detail(daily_load, order)

        # 平均日学习量应超过阈值
        assert detail.avg_daily_load_hours > fc.config.daily_load_threshold_hours
        assert detail.overload_ratio > 0

    def test_difficulty_density_for_consecutive_high(self, fitness_calc):
        """连续高难度知识点应增加密集度得分"""
        pos = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        order = fitness_calc._decode_order(pos)
        daily_load = fitness_calc._calculate_daily_load(order)
        density = fitness_calc._calculate_difficulty_density(daily_load, order)
        # kp_3 (diff=4) 和 kp_4 (diff=3) 和 kp_5 (diff=5) 可能连续
        assert density >= 0

    def test_empty_kps_no_crash(self):
        """空知识点不应崩溃, 空集无依赖违反 → feasible"""
        fc = build_fitness_calculator(knowledge_points=[], student_mastery={})
        pos = np.array([])
        result = fc.evaluate(pos)
        assert result.coverage == 0.0
        assert result.is_feasible  # 空集无依赖违反
        assert result.cognitive_load_score == 0.0


# ============================================================
# 测试: Pareto 前沿 & 路径分类 (新增)
# ============================================================


class TestParetoFront:
    """多目标 Pareto 前沿提取与路径分类"""

    def test_pareto_front_empty_for_no_results(self, fitness_calc):
        """空结果 → 空 Pareto 前沿"""
        pf = fitness_calc.compute_pareto_front([])
        assert isinstance(pf, ParetoFront)
        assert not pf.has_data
        assert pf.size == 0

    def test_pareto_front_only_feasible(self, fitness_calc):
        """只有可行解进入 Pareto 前沿"""
        # 构建混合结果 (1 个可行, 2 个不可行)
        pos_feasible = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        pos_infeasible = np.array([0.5, 0.4, 0.3, 0.2, 0.1])

        results = []
        results.append(fitness_calc.evaluate_strict(pos_feasible))
        results.append(fitness_calc.evaluate_strict(pos_infeasible))
        results.append(fitness_calc.evaluate_strict(pos_infeasible + 0.01))

        positions = np.array([pos_feasible, pos_infeasible, pos_infeasible + 0.01])

        pf = fitness_calc.compute_pareto_front(results, positions)

        # 应只有 1 个可行解在 Pareto 上
        assert pf.has_data
        for r in pf.fitness_results:
            assert r.is_feasible

    def test_pareto_path_classification(self, fitness_calc):
        """Pareto 前沿应分类为 efficiency/balanced/robust"""
        # 生成多种不同位置, 产生多个可行解
        feasible_positions = []
        for seed in range(10):
            pos = np.arange(5) * 0.12 + seed * 0.02
            result = fitness_calc.evaluate_strict(pos)
            if result.is_feasible:
                feasible_positions.append((pos.copy(), result))

        if len(feasible_positions) >= 3:
            positions_arr = np.array([p for p, _ in feasible_positions])
            results = [r for _, r in feasible_positions]
            pf = fitness_calc.compute_pareto_front(results, positions_arr)

            if pf.has_data and pf.size >= 3:
                # 应设置效率/平衡/稳健索引
                assert pf.efficiency_idx >= 0
                assert pf.balanced_idx >= 0
                assert pf.robust_idx >= 0
                assert pf.efficiency_idx < pf.size
                # 效率型和稳健型如果是同一个解, 合并标记
                all_types = {pf.fitness_results[i].path_type for i in range(pf.size)}
                assert len(all_types) >= 2  # 至少有 2 种类型

    def test_non_dominated_sort_correctness(self):
        """非支配排序应正确识别 Pareto 前沿"""
        # obj1: 越大越好, obj2: 越大越好
        obj1 = np.array([1.0, 0.8, 0.5, 0.2])
        obj2 = np.array([0.2, 0.5, 0.8, 1.0])

        mask = FitnessCalculator._non_dominated_sort(obj1, obj2)

        # [1.0, 0.2] 和 [0.2, 1.0] 互不支配, 都应在前沿上
        # [0.8, 0.5] 被 [1.0, 0.2] 部分支配 (obj1)，但不被完全支配
        # 实际上: [1.0, 0.2] dominates [0.8, 0.5]? 
        #   Yes: 1.0>=0.8 AND 0.2>=0.5? No. 0.2 < 0.5. So doesn't dominate.
        # [1.0, 0.2] dominates [0.5, 0.8]? No (0.2 < 0.8).
        # [1.0, 0.2] dominates [0.2, 1.0]? No (0.2 < 1.0).
        # So [1.0, 0.2] is non-dominated.
        # [0.2, 1.0] dominates [0.8, 0.5]? No (0.2 < 0.8).
        # [0.2, 1.0] dominates [0.5, 0.8]? No (0.2 < 0.5).
        # So all four are non-dominated!
        assert mask.sum() >= 2  # at least the two extremes

    def test_non_dominated_sort_with_clear_dominance(self):
        """明显被支配的点应被排除"""
        obj1 = np.array([1.0, 0.9, 0.5])
        obj2 = np.array([1.0, 0.9, 0.3])

        mask = FitnessCalculator._non_dominated_sort(obj1, obj2)

        # [1.0, 1.0] dominates both [0.9, 0.9] and [0.5, 0.3]
        assert bool(mask[0]) is True
        assert bool(mask[1]) is False
        assert bool(mask[2]) is False

    def test_evaluate_population_batch(self, fitness_calc):
        """批量评估应返回正确数量"""
        pop = np.random.rand(10, 5)
        fitnesses, results = fitness_calc.evaluate_population(pop)
        assert len(fitnesses) == 10
        assert len(results) == 10
        assert all(isinstance(r, FitnessResult) for r in results)

    def test_pareto_front_limits_size(self, fitness_calc):
        """Pareto 前沿应限制最大数量"""
        # 生成很多可行解
        results = []
        for i in range(20):
            pos = np.arange(5) * 0.1 + i * 0.01
            # 确保可行
            r = fitness_calc.evaluate_strict(pos)
            results.append(r)

        pf = fitness_calc.compute_pareto_front(results)
        # 应不超过 pareto_max_paths 限制
        assert pf.size <= fitness_calc.config.pareto_max_paths


# ============================================================
# 测试: 主循环 & 收敛
# ============================================================


class TestOptimizationLoop:
    """完整优化流程"""

    def test_full_optimization_runs(self, engine):
        result = engine.optimize()
        assert isinstance(result, OptimizationResult)
        assert result.best_position is not None
        assert result.best_fitness > -np.inf
        assert result.total_iterations > 0

    def test_convergence_data_complete(self, engine):
        result = engine.optimize()
        conv = result.convergence
        assert len(conv.iterations) == result.total_iterations
        assert len(conv.best_fitness) == result.total_iterations
        assert len(conv.avg_fitness) == result.total_iterations
        assert len(conv.diversity) == result.total_iterations

    def test_best_fitness_monotonic(self, engine):
        result = engine.optimize()
        best_f = result.convergence.best_fitness
        for i in range(1, len(best_f)):
            assert best_f[i] >= best_f[i - 1] - 1e-10

    def test_result_shape(self, engine):
        result = engine.optimize()
        assert result.best_position.shape == (engine.config.dim,)

    def test_best_position_in_bounds(self, engine):
        result = engine.optimize()
        assert np.all(result.best_position >= engine.config.lb)
        assert np.all(result.best_position <= engine.config.ub)

    def test_seed_reproducibility(self, simple_config, fitness_calc):
        config_a = AOOConfig(**{**simple_config.to_dict(), "seed": 42, "max_iterations": 20})
        engine_a = AOOEngine(config=config_a, fitness_calculator=fitness_calc)
        result_a = engine_a.optimize()
        config_b = AOOConfig(**{**simple_config.to_dict(), "seed": 42, "max_iterations": 20})
        engine_b = AOOEngine(config=config_b, fitness_calculator=fitness_calc)
        result_b = engine_b.optimize()
        assert result_a.best_fitness == result_b.best_fitness
        assert np.allclose(result_a.best_position, result_b.best_position)

    def test_log_entries_recorded(self, engine):
        result = engine.optimize()
        assert len(result.log_entries) == result.total_iterations
        for entry in result.log_entries:
            assert "iteration" in entry
            assert "best_fitness" in entry


# ============================================================
# 测试: 边界约束
# ============================================================


class TestBounds:
    """边界约束"""

    def test_clipping_works(self, engine):
        engine._initialize_population()
        engine._population[0, 0] = 100.0
        engine._population[0, 1] = -100.0
        engine._apply_bounds()
        assert engine._population[0, 0] == engine.config.ub
        assert engine._population[0, 1] == engine.config.lb

    def test_no_out_of_bounds_after_optimization(self, engine):
        result = engine.optimize()
        final_pop = result.final_population
        assert np.all(final_pop >= engine.config.lb)
        assert np.all(final_pop <= engine.config.ub)


# ============================================================
# 测试: 早停机制
# ============================================================


class TestEarlyStop:
    """早停"""

    def test_early_stop_triggers_on_stagnation(self):
        config = AOOConfig(
            population_size=10, dim=5, max_iterations=200,
            early_stop_patience=5, early_stop_tolerance=1e-6, seed=42,
        )
        kps = [{"id": f"kp_{i}", "name": f"KP{i}", "difficulty": 2,
                "layer": "basic", "prerequisites": [], "estimated_hours": 0.5}
               for i in range(5)]
        mastery = {f"kp_{i}": 0.5 for i in range(5)}
        fc = build_fitness_calculator(knowledge_points=kps, student_mastery=mastery, config=config)
        eng = AOOEngine(config=config, fitness_calculator=fc)
        eng._initialize_population()
        eng._fitness = np.ones(10)
        eng._best_fitness = 100.0
        eng._best_position = eng._population[0].copy()
        conv_dummy = eng._populate_dummy_convergence(20, 100.0)
        assert eng._check_early_stop(conv_dummy, stagnation_counter=10)


# ============================================================
# 测试: 配置系统
# ============================================================


class TestConfig:
    """AOO 配置"""

    def test_default_config_creation(self):
        config = AOOConfig()
        assert config.population_size == 50
        assert config.max_iterations == 500

    def test_env_var_override(self):
        with patch.dict(os.environ, {"AOO_POPULATION_SIZE": "100", "AOO_SEED": "999"}):
            config = AOOConfig()
            assert config.population_size == 100
            assert config.seed == 999

    def test_env_var_bool(self):
        with patch.dict(os.environ, {"AOO_USE_ADAPTIVE_PARAMS": "false"}):
            config = AOOConfig()
            assert config.use_adaptive_params is False

    def test_new_params_defaults(self):
        """新参数应有正确默认值"""
        config = AOOConfig()
        assert config.coverage_weight == 0.3
        assert config.mastery_weight == 0.7
        assert config.forgetting_factor == 0.85
        assert config.base_learning_gain == 0.15
        assert config.daily_load_threshold_hours == 3.0
        assert config.difficulty_density_weight == 0.3
        assert config.pareto_enabled is True

    def test_to_dict(self):
        config = AOOConfig(population_size=25, seed=123)
        d = config.to_dict()
        assert d["population_size"] == 25
        assert d["seed"] == 123

    def test_bounds_property(self):
        config = AOOConfig(lb=-1.0, ub=2.0)
        assert config.bounds == (-1.0, 2.0)


# ============================================================
# 测试: 多样性计算 & 精英保留
# ============================================================


class TestDiversity:
    """种群多样性"""

    def test_diversity_range(self, engine):
        engine._initialize_population()
        engine._fitness = np.random.randn(engine.config.population_size)
        div = engine._calculate_diversity()
        assert 0.0 <= div <= 1.0

    def test_diversity_zero_for_identical(self, engine):
        engine._initialize_population()
        engine._population = np.ones((engine.config.population_size, engine.config.dim)) * 0.5
        engine._fitness = np.zeros(engine.config.population_size)
        div = engine._calculate_diversity()
        assert div == 0.0


class TestElitism:
    """精英保留"""

    def test_best_is_preserved(self, engine):
        engine._initialize_population()
        N = engine.config.population_size
        Dim = engine.config.dim
        engine._population[0] = np.full(Dim, 0.12345)
        engine._fitness = np.zeros(N)
        engine._best_fitness = 9999.0
        engine._best_position = engine._population[0].copy()
        engine._evaluate_and_elitism()
        assert np.any(np.all(engine._population == engine._best_position, axis=1))


# ============================================================
# 测试: Factory 函数
# ============================================================


class TestBuildFitnessCalculator:
    """工厂函数"""

    def test_creates_valid_calculator(self, sample_kps, student_mastery):
        fc = build_fitness_calculator(
            knowledge_points=sample_kps, student_mastery=student_mastery,
        )
        assert isinstance(fc, FitnessCalculator)
        assert len(fc.kps) == 5

    def test_handles_empty_data(self):
        fc = build_fitness_calculator(knowledge_points=[], student_mastery={})
        assert len(fc.kps) == 0


# ============================================================
# 集成测试 (含 Pareto 路径)
# ============================================================


class TestIntegration:
    """端到端集成测试"""

    def test_small_scale_full_pipeline(self, simple_config):
        """小规模完整流程: 初始化 → 优化 → 收敛"""
        kps = [
            {
                "id": f"kp_{i}",
                "name": f"知识点{i}",
                "difficulty": float(i % 5 + 1),
                "layer": ["basic", "core", "advanced"][i % 3],
                "prerequisites": [f"kp_{i-1}"] if i > 0 else [],
                "estimated_hours": 1.0 + i * 0.5,
            }
            for i in range(10)
        ]
        mastery = {f"kp_{i}": 1.0 - i * 0.1 for i in range(10)}

        fc = build_fitness_calculator(knowledge_points=kps, student_mastery=mastery, config=simple_config)
        config = AOOConfig(**{**simple_config.to_dict(), "dim": 10})
        eng = AOOEngine(config=config, fitness_calculator=fc)

        result = eng.optimize()

        assert result.total_iterations > 0
        assert result.total_time_seconds > 0
        assert result.best_fitness > -np.inf

    def test_convergence_curve_has_improvement(self, simple_config):
        """收敛曲线应显示适应度改进"""
        config = AOOConfig(**{
            **simple_config.to_dict(), "dim": 5, "max_iterations": 30, "population_size": 15,
        })
        kps = [
            {"id": f"kp_{i}", "name": f"P{i}", "difficulty": 3, "layer": "core",
             "prerequisites": [], "estimated_hours": 1.0}
            for i in range(5)
        ]
        mastery = {f"kp_{i}": 0.5 for i in range(5)}
        fc = build_fitness_calculator(knowledge_points=kps, student_mastery=mastery, config=config)
        eng = AOOEngine(config=config, fitness_calculator=fc)

        result = eng.optimize()

        first_best = result.convergence.best_fitness[0]
        last_best = result.convergence.best_fitness[-1]
        assert last_best >= first_best - 1e-10

    def test_final_population_feasibility(self, simple_config):
        """无前置依赖的知识点: 最终种群应包含可行解"""
        config = AOOConfig(**{
            **simple_config.to_dict(), "dim": 5, "max_iterations": 30, "population_size": 20,
        })
        kps = [
            {"id": f"kp_{i}", "name": f"KP{i}", "difficulty": 3, "layer": "core",
             "prerequisites": [], "estimated_hours": 1.0}
            for i in range(5)
        ]
        mastery = {f"kp_{i}": 0.5 for i in range(5)}
        fc = build_fitness_calculator(knowledge_points=kps, student_mastery=mastery, config=config)
        eng = AOOEngine(config=config, fitness_calculator=fc)

        result = eng.optimize()

        # 无前置依赖, 所有顺序都可行
        _, final_results = fc.evaluate_population(result.final_population)
        feasible_count = sum(1 for r in final_results if r.is_feasible)
        assert feasible_count == len(final_results)

    def test_pareto_front_with_multiple_feasible(self, simple_config):
        """多可行解 → 产生 Pareto 前沿"""
        config = AOOConfig(**{
            **simple_config.to_dict(), "dim": 5, "max_iterations": 50, "population_size": 20,
            "pareto_enabled": True,
        })
        # 无前置依赖链 → 所有解都可行
        kps = [
            {"id": f"kp_{i}", "name": f"X{i}", "difficulty": float(i % 5 + 1),
             "layer": ["basic", "core", "advanced"][i % 3],
             "prerequisites": [], "estimated_hours": 0.5 + i * 0.3}
            for i in range(5)
        ]
        mastery = {f"kp_{i}": i * 0.2 for i in range(5)}
        fc = build_fitness_calculator(knowledge_points=kps, student_mastery=mastery, config=config)
        eng = AOOEngine(config=config, fitness_calculator=fc)

        result = eng.optimize()

        _, final_results = fc.evaluate_population(result.final_population)
        pf = fc.compute_pareto_front(final_results, result.final_population)

        # 应有 Pareto 前沿
        assert pf.has_data
        assert pf.size >= 1
        if pf.size >= 3:
            assert pf.efficiency_idx >= 0
            assert pf.balanced_idx >= 0
            assert pf.robust_idx >= 0
