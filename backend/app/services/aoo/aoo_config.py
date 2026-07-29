"""AOO 算法配置模块 — 所有参数可通过环境变量覆盖

对应论文《The Animated Oat Optimization Algorithm》的超参数体系。
"""

import os
from dataclasses import dataclass, field
from typing import Tuple


@dataclass
class AOOConfig:
    """AOO 优化器配置

    所有字段均可通过大写环境变量 AOO_<FIELD> 覆盖。
    数值型参数支持 int / float 自动类型转换。
    """

    # ============================================================
    # 种群参数
    # ============================================================
    population_size: int = 50          # N: 种群规模
    dim: int = 20                      # Dim: 解空间维度 (知识点数量)
    lb: float = 0.0                    # LB: 下界
    ub: float = 1.0                    # UB: 上界

    # ============================================================
    # 迭代控制
    # ============================================================
    max_iterations: int = 500          # T_max: 最大迭代次数
    early_stop_patience: int = 50      # 早停忍耐代数 (无改进则停止)
    early_stop_tolerance: float = 1e-6 # 早停改进阈值

    # ============================================================
    # 探索/开发阶段控制
    # ============================================================
    exploration_rate: float = 0.3      # 探索概率 (前中期高)
    levy_beta: float = 1.5             # Lévy 飞行参数 β
    levy_sigma: float = 0.01           # Lévy 飞行缩放因子

    # ============================================================
    # 种群快照采样
    # ============================================================
    snapshot_interval: int = 10        # 每隔多少代保存一次种群快照
    max_snapshots: int = 50            # 最多保留快照数

    # ============================================================
    # 随机种子
    # ============================================================
    seed: int = 42

    # ============================================================
    # 适应度函数权重 (教育场景)
    # ============================================================
    alpha: float = 0.6                 # 学习效果权重
    beta: float = 0.4                  # 认知负荷得分权重
    prerequisite_penalty: float = -1e9  # 前置依赖违反惩罚 (硬约束, fitness → -∞)
    coverage_weight: float = 0.3       # 知识图谱覆盖率在学习效果中的权重
    mastery_weight: float = 0.7        # 掌握度提升在学习效果中的权重

    # ============================================================
    # 学习效果模型参数
    # ============================================================
    forgetting_factor: float = 0.85    # 遗忘因子 (艾宾浩斯曲线, 越大遗忘越慢)
    base_learning_gain: float = 0.15   # 基础学习增益 (每学习一个前置知识点的掌握度提升)
    mastery_gain_cap: float = 1.0      # 掌握度上限

    # ============================================================
    # 认知负荷评估参数
    # ============================================================
    daily_load_threshold_hours: float = 3.0   # 单日学习量阈值 (小时)
    difficulty_density_weight: float = 0.3     # 难度密集度权重
    high_difficulty_threshold: float = 4.0     # 高难度判定阈值
    consecutive_high_difficulty_penalty: float = 0.5  # 连续高难度惩罚系数

    # ============================================================
    # Pareto 多目标 / 路径分类
    # ============================================================
    pareto_enabled: bool = True        # 是否启用 Pareto 前沿提取
    pareto_max_paths: int = 10         # Pareto 前沿最多保留路径数
    path_type_weights: Tuple[float, float, float] = field(
        default_factory=lambda: (0.7, 0.5, 0.3)
    )  # 效率型/平衡型/稳健型 的学习效果偏好权重

    # ============================================================
    # 算法变体
    # ============================================================
    use_adaptive_params: bool = True   # 是否使用自适应参数

    def __post_init__(self) -> None:
        """从环境变量覆盖默认值"""
        self._load_from_env()

    def _load_from_env(self) -> None:
        """读取 AOO_* 环境变量并覆盖对应字段"""
        for field_name in self.__dataclass_fields__:
            env_key = f"AOO_{field_name.upper()}"
            env_val = os.getenv(env_key)
            if env_val is not None:
                field_type = type(getattr(self, field_name))
                if field_type is bool:
                    setattr(self, field_name, env_val.lower() in ("true", "1", "yes"))
                else:
                    setattr(self, field_name, field_type(env_val))

    @property
    def bounds(self) -> Tuple[float, float]:
        """返回 (LB, UB) 元组"""
        return (self.lb, self.ub)

    def to_dict(self) -> dict:
        """序列化为字典 (用于日志记录)"""
        return {
            f.name: getattr(self, f.name)
            for f in self.__dataclass_fields__.values()
            if not f.name.startswith("_")
        }


# ============================================================
# 全局默认配置实例
# ============================================================
default_config = AOOConfig()
