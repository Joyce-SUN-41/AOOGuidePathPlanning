"""诊断模块 Pydantic Schema — 认知诊断测验的请求/响应数据模型

与前端 src/types/index.ts 中的 Diagnosis* 类型严格同步。
字段使用 Python snake_case 定义，通过 CamelModel 自动输出 camelCase JSON。
"""

from datetime import datetime
from typing import List, Optional

from pydantic import Field

from app.schemas.aoo import CamelModel


# ═══════════ 题目相关 ═══════════

class DiagnosisOption(CamelModel):
    """诊断题目的选项"""
    id: str = Field(..., description="选项 ID，如 A/B/C/D")
    text: str = Field(..., description="选项文本")
    weight: float = Field(default=0.0, description="掌握度权重 0-1")


class DiagnosisQuestion(CamelModel):
    """诊断题目"""
    id: str = Field(..., description="题目唯一标识")
    topic: str = Field(..., description="所属知识点名称")
    kp_id: str = Field(default="", description="知识点 ID")
    difficulty: int = Field(default=1, ge=1, le=5, description="难度 1-5")
    title: str = Field(..., description="题目内容")
    options: List[DiagnosisOption] = Field(default_factory=list, description="选项列表")
    type: str = Field(default="single", description="题型: single / multiple")
    correct_option_id: str = Field(default="", description="正确答案选项 ID")
    expected_time_sec: float = Field(default=20.0, description="预期答题时间(秒)")


class QuestionsResponse(CamelModel):
    """获取题目的响应"""
    questions: List[DiagnosisQuestion] = Field(default_factory=list)
    total: int = Field(default=0)
    subject: str = Field(default="")
    estimated_duration_min: int = Field(default=5, description="预计完成时间(分钟)")


# ═══════════ 提交答案 ═══════════

class SubmittedAnswer(CamelModel):
    """用户提交的单题答案"""
    question_id: str = Field(..., description="题目 ID")
    selected_option: str = Field(..., description="用户选择的选项 ID")
    time_spent: float = Field(default=0.0, description="答题耗时(秒)")


class DiagnosisSubmitRequest(CamelModel):
    """诊断提交请求体"""
    answers: List[SubmittedAnswer] = Field(..., min_length=1, description="答案列表")
    subject: str = Field(default="人工智能导论", description="学科")
    grade: str = Field(default="", description="年级")
    student_id: Optional[str] = Field(default=None, description="学生 ID (服务端自动注入)")


# ═══════════ 诊断结果 ═══════════

class MasteryItem(CamelModel):
    """单个知识点的掌握度"""
    knowledge_point: str = Field(..., description="知识点名称")
    kp_id: str = Field(default="", description="知识点 ID")
    mastery: float = Field(..., ge=0.0, le=1.0, description="掌握度 0-1")
    level: str = Field(default="developing", description="等级: weak/developing/proficient/excellent")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="置信度 0-1")


class CognitiveLoadProfile(CamelModel):
    """认知负荷多维度分析"""
    memory_load: float = Field(default=0.0, ge=0.0, le=1.0, description="记忆负荷")
    attention_load: float = Field(default=0.0, ge=0.0, le=1.0, description="注意力负荷")
    processing_load: float = Field(default=0.0, ge=0.0, le=1.0, description="加工负荷")
    overall: float = Field(default=0.0, ge=0.0, le=1.0, description="综合负荷")


class WeakPoint(CamelModel):
    """薄弱知识点"""
    kp_id: str = Field(default="", description="知识点 ID")
    knowledge_point: str = Field(..., description="知识点名称")
    reason: str = Field(default="", description="薄弱原因")
    severity: str = Field(default="mild", description="严重度: mild/moderate/severe")
    suggested_remediation: str = Field(default="", description="改进建议")


class RadarPoint(CamelModel):
    """雷达图数据点"""
    dimension: str = Field(..., description="维度名称")
    value: float = Field(..., ge=0.0, le=1.0, description="维度值")


class DiagnosisResultResponse(CamelModel):
    """诊断结果完整响应"""
    id: str = Field(..., description="诊断记录 ID")
    user_id: str = Field(..., description="用户 ID")
    created_at: datetime = Field(..., description="创建时间")
    subject: str = Field(default="", description="学科")
    grade: str = Field(default="", description="年级")

    mastery_levels: List[MasteryItem] = Field(default_factory=list, description="知识点掌握度列表")
    cognitive_load: CognitiveLoadProfile = Field(
        default_factory=CognitiveLoadProfile, description="认知负荷分析"
    )
    learning_style: str = Field(default="", description="学习风格标签")
    weak_points: List[WeakPoint] = Field(default_factory=list, description="薄弱点列表")
    overall_score: float = Field(default=0.0, description="综合评分 0-100")
    summary: str = Field(default="", description="AI 诊断摘要")
    radar_data: List[RadarPoint] = Field(default_factory=list, description="雷达图数据")
    cognitive_load_index: float = Field(default=0.0, description="认知负荷指数")


class RawDiagnosisResult(CamelModel):
    """原始诊断结果 (简化结构，兼容旧 API)"""
    mastery_levels: dict = Field(default_factory=dict, description="{kp_id: value}")
    cognitive_load: float = Field(default=0.0, description="综合认知负荷")
    weak_points: List[str] = Field(default_factory=list, description="薄弱知识点 ID 列表")
    diagnosis_id: str = Field(default="", description="诊断记录 ID")
    radar_data: dict = Field(default_factory=dict, description="{维度名: 值}")


# ═══════════ 诊断历史 ═══════════

class DiagnosisBrief(CamelModel):
    """诊断历史简要条目"""
    id: str = Field(..., description="诊断记录 ID")
    created_at: datetime = Field(..., description="创建时间")
    subject: str = Field(default="", description="学科")
    overall_score: float = Field(default=0.0, description="综合评分")
    weak_point_count: int = Field(default=0, description="薄弱点数量")


class DiagnosisHistoryResponse(CamelModel):
    """诊断历史列表响应"""
    items: List[DiagnosisBrief] = Field(default_factory=list)
    total: int = Field(default=0)
