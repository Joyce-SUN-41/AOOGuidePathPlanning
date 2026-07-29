"""
AOO 可视化数据接口契约 — Pydantic v2 模式

与前端 src/types/aoo.ts 严格同步。
字段使用 Python snake_case 定义，通过 alias_generator 自动输出 camelCase JSON。
前端 axios 拦截器无需再做 key 转换。
"""

import re
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


def _to_camel(s: str) -> str:
    """snake_case → camelCase"""
    parts = s.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


# ---- 自动 camelCase 别名生成器 ----
#   所有继承此类的 Pydantic 模型，JSON 输出 key 均为小驼峰
#   同时支持输入 snake_case 和 camelCase (populate_by_name=True)


class CamelModel(BaseModel):
    """Pydantic 基类：自动 snsake_case → camelCase JSON 序列化"""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,  # 允许用 snake_case 赋值
        from_attributes=True,   # 允许从 ORM 模型构建
        extra="forbid",         # 拒绝未定义字段
    )


# ============================================================
# 种群快照 & 收敛曲线数据
# ============================================================


class PopulationSnapshot(CamelModel):
    """单个迭代的种群个体分布 — 前端散点图动画"""

    fitness_values: List[float] = Field(..., description="个体适应度值列表")
    positions_x: List[float] = Field(..., description="个体在解空间中的 x 坐标（降维后）")
    positions_y: List[float] = Field(..., description="个体在解空间中的 y 坐标（降维后）")
    colors: List[str] = Field(..., description="颜色标签：'elite' | 'normal' | 'exploring'")
    best_index: int = Field(..., description="该迭代最佳个体索引", ge=0)


class ConvergenceMetadata(CamelModel):
    """收敛过程元信息"""

    algorithm: str = Field(default="AOO", description="算法名称")
    population_size: int = Field(..., description="种群规模", ge=1)
    elite_count: int = Field(..., description="精英保留数", ge=0)
    convergence_rate: float = Field(..., description="最终收敛率 [0, 1]", ge=0, le=1)
    convergence_iteration: int = Field(
        ..., description="收敛所需代数（达到最优解 95% 的代数）", ge=0
    )
    total_time_seconds: float = Field(..., description="总优化耗时（秒）", ge=0)


class AOOConvergenceData(CamelModel):
    """AOO 收敛曲线全部数据 — 前端图表直接消费"""

    iterations: List[int] = Field(..., description="迭代轮次序列 [1, 2, 3, ...]")
    best_fitness: List[float] = Field(..., description="每代最佳适应度，单调非递减")
    avg_fitness: List[float] = Field(..., description="每代平均适应度")
    diversity: List[float] = Field(..., description="每代种群多样性 [0, 1]")
    median_fitness: List[float] = Field(..., description="每代中位数适应度")
    q1_fitness: List[float] = Field(..., description="每代第一四分位数 Q1")
    q3_fitness: List[float] = Field(..., description="每代第三四分位数 Q3")
    population_snapshots: Optional[List[PopulationSnapshot]] = Field(
        default=None, description="种群快照 — 用于散点图动画"
    )
    metadata: ConvergenceMetadata = Field(..., description="收敛元信息")


# ============================================================
# 学习路径结构
# ============================================================


class PathTaskInDay(CamelModel):
    """路径中的单个学习任务"""

    name: str = Field(..., description="任务名称")
    duration: int = Field(..., description="预估耗时（分钟）", ge=0)
    type: str = Field(
        ...,
        description="任务类型",
        pattern=r"^(video|quiz|reading|project|exercise)$",
    )
    knowledge_point: Optional[str] = Field(default=None, description="关联知识点")
    difficulty: Optional[int] = Field(default=None, description="难度 1-5", ge=1, le=5)


class PathDay(CamelModel):
    """路径中的一天"""

    day: int = Field(..., description="第几天（从 1 开始）", ge=1)
    tasks: List[PathTaskInDay] = Field(..., description="当天任务列表")
    total_minutes: int = Field(..., description="当天总预估耗时（分钟）", ge=0)
    avg_difficulty: float = Field(..., description="当天平均难度", ge=1, le=5)


class BestPath(CamelModel):
    """AOO 计算的最优路径"""

    days: List[PathDay] = Field(..., description="按天组织的学习路径")
    total_fitness: float = Field(..., description="适应度得分 [0, 1]", ge=0, le=1)
    total_days: int = Field(..., description="总天数", ge=0)
    total_tasks: int = Field(..., description="总任务数", ge=0)
    total_estimated_hours: float = Field(..., description="总预估小时数", ge=0)


class AOOLearningPathResult(CamelModel):
    """AOO 生成结果 — 嵌入任务状态响应的 result 字段"""

    best_path: BestPath = Field(..., description="最优路径")
    convergence: AOOConvergenceData = Field(..., description="收敛数据 — 前端直接绑定图表")


# ============================================================
# 对外暴露：API 响应体
# ============================================================


class AOOLearningPathResponse(CamelModel):
    """GET /api/v1/path/task/{taskId} — 任务状态轮询响应"""

    task_id: str = Field(..., description="异步任务 ID")
    status: str = Field(
        ...,
        description="任务状态",
        pattern=r"^(pending|queued|processing|completed|failed)$",
    )
    progress: float = Field(default=0, description="进度百分比 [0, 100]", ge=0, le=100)
    result: Optional[AOOLearningPathResult] = Field(
        default=None, description="完成后返回路径 + 收敛数据"
    )
    error_message: Optional[str] = Field(default=None, description="失败时的错误信息")
    estimated_remaining_seconds: Optional[float] = Field(
        default=None, description="预估剩余秒数", ge=0
    )


# ============================================================
# 请求体类型
# ============================================================


class AOOPreferencesModel(CamelModel):
    """AOO 优化偏好参数"""

    max_days: Optional[int] = Field(default=None, description="最大学习天数", ge=1)
    focus_areas: Optional[List[str]] = Field(
        default=None, description="重点关注的薄弱知识点"
    )
    intensity: Optional[str] = Field(
        default=None,
        description="学习强度",
        pattern=r"^(light|moderate|intensive)$",
    )
    max_daily_minutes: Optional[int] = Field(
        default=None, description="每日最大学习时长（分钟）", ge=30
    )
    population_size: Optional[int] = Field(
        default=50, description="种群规模", ge=10, le=500
    )
    max_iterations: Optional[int] = Field(
        default=200, description="最大迭代次数", ge=10, le=2000
    )


class AOOGenerateRequest(CamelModel):
    """POST /api/v1/path/generate — 触发 AOO 路径生成"""

    diagnosis_id: str = Field(..., description="诊断结果 ID")
    preferences: Optional[AOOPreferencesModel] = Field(
        default=None, description="可选的偏好配置"
    )
