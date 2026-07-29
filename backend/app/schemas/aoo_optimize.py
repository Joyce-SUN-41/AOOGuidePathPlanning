"""
AOO 路径规划优化 API 的 Pydantic v2 请求/响应 Schema

POST /api/v1/aoo/optimize — 触发 AOO 路径优化
GET  /api/v1/aoo/status/{task_id} — 轮询任务状态
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.aoo import (
    AOOConvergenceData,
    BestPath,
    CamelModel,
    PathDay,
    PathTaskInDay,
)


# ============================================================
# 请求体
# ============================================================


class AOOOptimizeConfig(CamelModel):
    """AOO 优化超参数配置"""

    population_size: int = Field(
        default=50, ge=10, le=500, description="种群规模"
    )
    max_iterations: int = Field(
        default=500, ge=10, le=2000, description="最大迭代次数"
    )
    alpha: float = Field(
        default=0.6, ge=0.1, le=1.0, description="学习效果权重"
    )
    beta: float = Field(
        default=0.4, ge=0.1, le=1.0, description="认知负荷权重"
    )
    max_days: Optional[int] = Field(
        default=None, ge=1, le=60, description="最大学习天数"
    )
    max_daily_minutes: Optional[int] = Field(
        default=None, ge=30, le=480, description="每日最大学习时长(分钟)"
    )
    seed: Optional[int] = Field(
        default=None, ge=0, description="随机种子 (可复现性)"
    )


class AOOOptimizeRequest(CamelModel):
    """POST /api/v1/aoo/optimize — 触发 AOO 路径优化"""

    student_id: str = Field(..., description="学生用户 ID (UUID)")
    diagnosis_id: str = Field(..., description="诊断结果 ID")
    mastery_levels: Dict[str, float] = Field(
        ..., description="知识点掌握度映射 {kp_id: value ∈ [0,1]}"
    )
    cognitive_load: float = Field(
        ..., ge=0.0, le=1.0, description="综合认知负荷指数"
    )
    config: Optional[AOOOptimizeConfig] = Field(
        default=None, description="可选的 AOO 超参数覆盖"
    )

    @field_validator("mastery_levels")
    @classmethod
    def mastery_values_in_range(cls, v: Dict[str, float]) -> Dict[str, float]:
        """确保所有掌握度值在 [0, 1] 范围内"""
        for kp_id, value in v.items():
            if not (0.0 <= value <= 1.0):
                raise ValueError(
                    f"知识点 {kp_id} 的掌握度 {value} 不在 [0, 1] 范围内"
                )
        return v


# ============================================================
# 收敛数据 (增量上报)
# ============================================================


class ConvergenceSnapshot(CamelModel):
    """单次迭代的收敛数据点 — 由 AOO 引擎每代回调上报到 Redis

    前端轮询 GET /status/{task_id} 时, 将 Redis 中累积的 ConvergenceSnapshot
    列表聚合为 ConvergencePoint 返回。
    """

    iteration: int = Field(..., ge=0, description="迭代轮次")
    best_fitness: float = Field(..., description="当前最佳适应度")
    avg_fitness: float = Field(..., description="当前平均适应度")
    diversity: float = Field(default=0, description="种群多样性")


class ConvergencePoint(CamelModel):
    """聚合后的收敛曲线数据 — 供前端绘制实时收敛图

    从 Redis 累积的 ConvergenceSnapshot 列表中提取 iteration/best_fitness/avg_fitness 三组数组。
    """

    iterations: List[int] = Field(default_factory=list, description="迭代轮次序列")
    best_fitness: List[float] = Field(default_factory=list, description="最佳适应度序列")
    avg_fitness: List[float] = Field(default_factory=list, description="平均适应度序列")


# ============================================================
# 响应体
# ============================================================


class AlternativePath(CamelModel):
    """备选路径 (Pareto 前沿中的一条)"""

    path_type: str = Field(
        ..., description="路径类型", pattern=r"^(efficiency|balanced|robust)$"
    )
    days: List[PathDay] = Field(..., description="按天组织")
    total_days: int = Field(..., ge=0)
    total_tasks: int = Field(..., ge=0)
    total_estimated_hours: float = Field(..., ge=0)
    fitness: float = Field(..., ge=0, le=1, description="适应度得分")


class PathFitnessDetail(CamelModel):
    """路径适应度详情"""

    total_fitness: float
    learning_effect: float
    coverage: float
    mastery_improvement: float
    avg_final_mastery: float
    cognitive_load_score: float
    daily_load_score: float
    difficulty_density: float
    prerequisite_violations: int
    is_feasible: bool
    path_type: str


class AOOOptimizeResult(CamelModel):
    """AOO 优化生成的核心结果"""

    best_path: BestPath = Field(..., description="最优路径")
    fitness_detail: PathFitnessDetail = Field(..., description="最优路径适应度详情")
    alternative_paths: List[AlternativePath] = Field(
        default_factory=list, description="其他 Pareto 最优路径"
    )
    convergence_data: AOOConvergenceData = Field(..., description="收敛曲线数据")
    pareto_front: Dict[str, Any] = Field(
        default_factory=dict, description="Pareto 前沿序列化数据"
    )
    execution_time: float = Field(
        ..., ge=0, description="优化耗时 (秒)"
    )


class AOOOptimizeResponse(CamelModel):
    """POST /api/v1/aoo/optimize 同步响应 (返回即 completed)"""

    task_id: str = Field(..., description="任务 ID")
    status: str = Field(
        default="completed",
        description="任务状态",
        pattern=r"^(pending|queued|processing|completed|failed)$",
    )
    progress: float = Field(default=100, ge=0, le=100, description="进度百分比")
    result: Optional[AOOOptimizeResult] = Field(
        default=None, description="优化结果"
    )
    error_message: Optional[str] = Field(default=None, description="错误信息")


class AOOTaskStatusResponse(CamelModel):
    """GET /api/v1/aoo/status/{task_id} 任务状态轮询响应

    被前端以 1-2 秒间隔轮询, 用于:
      - 显示实时进度条
      - 绘制实时收敛曲线 (convergence_data)
      - 超时后显示错误信息
      - 完成后展示完整结果

    注意: progress 范围为 0~1 (不是百分比), 与 POST /optimize 立即返回的
          AOOOptimizeResponse (progress: 0-100) 区分开来。
    """

    task_id: str = Field(..., description="Celery 任务 ID")
    status: str = Field(
        ...,
        description="任务状态: pending | processing | completed | failed",
        pattern=r"^(pending|processing|completed|failed)$",
    )
    progress: float = Field(
        default=0, ge=0, le=1, description="进度 (0~1), 前端乘以 100 显示百分比"
    )
    current_iteration: int = Field(
        default=0, ge=0, description="当前迭代轮次 (算法行为)"
    )
    max_iterations: int = Field(
        default=0, ge=0, description="最大迭代轮次 (配置项)"
    )
    current_best_fitness: Optional[float] = Field(
        default=None, description="当前最佳适应度值, 前端用于显示"
    )
    convergence_data: Optional[ConvergencePoint] = Field(
        default=None,
        description=(
            "逐步累积的收敛数据, 用于前端实时绘制收敛曲线。"
            "processing 状态下持续增长, completed 后返回完整数据。"
        ),
    )
    result: Optional[AOOOptimizeResult] = Field(
        default=None, description="completed 时返回完整优化结果"
    )
    error: Optional[str] = Field(
        default=None, description="failed 时返回错误信息"
    )
    created_at: Optional[datetime] = Field(
        default=None, description="任务创建时间 (ISO 8601)"
    )
    updated_at: Optional[datetime] = Field(
        default=None, description="最后状态更新时间 (ISO 8601)"
    )
