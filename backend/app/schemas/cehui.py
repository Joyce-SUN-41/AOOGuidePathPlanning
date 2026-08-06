"""测绘模块 Pydantic Schema — 学情测绘测验的请求/响应数据模型

与前端 src/types/index.ts 中的 Cehui* 类型严格同步。
字段使用 Python snake_case 定义，通过 CamelModel 自动输出 camelCase JSON。
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import Field

from app.schemas.aoo import CamelModel


# ═══════════ 题目相关 ═══════════

class CehuiOption(CamelModel):
    """测绘题目的选项"""
    id: str = Field(..., description="选项 ID，如 A/B/C/D")
    text: str = Field(..., description="选项文本")
    weight: float = Field(default=0.0, description="掌握度权重 0-1")


class CehuiQuestion(CamelModel):
    """测绘题目"""
    id: str = Field(..., description="题目唯一标识")
    topic: str = Field(..., description="所属知识点名称")
    kp_id: str = Field(default="", description="知识点 ID")
    difficulty: int = Field(default=1, ge=1, le=5, description="难度 1-5")
    title: str = Field(..., description="题目内容")
    options: List[CehuiOption] = Field(default_factory=list, description="选项列表")
    type: str = Field(default="single", description="题型: single / multiple")
    correct_option_id: str = Field(default="", description="正确答案选项 ID")
    expected_time_sec: float = Field(default=20.0, description="预期答题时间(秒)")


class QuestionsResponse(CamelModel):
    """获取题目的响应"""
    questions: List[CehuiQuestion] = Field(default_factory=list)
    total: int = Field(default=0)
    subject: str = Field(default="")
    estimated_duration_min: int = Field(default=5, description="预计完成时间(分钟)")
    allocation: Dict[str, Dict[str, int]] = Field(
        default_factory=dict,
        description=(
            "图谱均衡组卷明细: {kp_id: {层级: 题数}}。图谱驱动抽题时返回,"
            "随机抽题(Mock/无图谱)时为空 dict, 前端可据其展示组卷均衡度。"
        ),
    )
    graph_driven: bool = Field(
        default=False,
        description="本次抽题是否由知识图谱驱动(否则为随机抽题降级)",
    )


# ═══════════ 提交答案 ═══════════

class SubmittedAnswer(CamelModel):
    """用户提交的单题答案"""
    question_id: str = Field(..., description="题目 ID")
    selected_option: str = Field(..., description="用户选择的选项 ID")
    time_spent: float = Field(default=0.0, description="答题耗时(秒)")


class CehuiSubmitRequest(CamelModel):
    """测绘提交请求体"""
    answers: List[SubmittedAnswer] = Field(..., min_length=1, description="答案列表")
    subject: str = Field(default="人工智能导论", description="学科")
    grade: str = Field(default="", description="年级")
    student_id: Optional[str] = Field(default=None, description="学生 ID (服务端自动注入)")
    # 第三维「学习准备度」轻量自陈量表（建议 3），可选；不填则走二维模式
    readiness: Optional["ReadinessProfile"] = Field(
        default=None, description="学习准备度自陈结果，可选；不填则仅用认知起点+学习风格"
    )
    # 学习风格自陈量表（建议 4），可选；不填则 learning_style 保持"未评估"，规划器关闭风格偏置
    style_items: Optional[List["StyleItem"]] = Field(
        default=None, description="学习风格自陈题项列表（6-8 题），可选；不填则风格偏置关闭"
    )


class StyleItem(CamelModel):
    """学习风格自陈量表单项（likert 1-5，可扩展）"""
    key: str = Field(..., description="题项标识，前缀 ambitious_/sequential_/steady_/exploratory_ 对应四风格")
    value: int = Field(..., ge=1, le=5, description="likert 自评 1-5")


class LearningStyleProfile(CamelModel):
    """学习风格画像（建议 4 独立自变量）

    label 为主风格标签（进取型/顺序型/踏实型/探索型），
    scores 为四风格维度归一化得分 0-1。
    """
    label: str = Field(default="未评估", description="主风格标签")
    scores: Dict[str, float] = Field(
        default_factory=dict,
        description="四风格维度得分 {ambitious, sequential, steady, exploratory} 0-1",
    )
    # 条目4/6: 风格剖面（主导+辅助）+ 强度
    primary_dimension: Optional[str] = Field(
        default=None, description="主导风格 key（如 exploratory）；全 0 时为 None"
    )
    secondary_dimension: Optional[str] = Field(
        default=None, description="辅助风格 key（得分次高的维度）；无则 None"
    )
    intensity: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="风格强度 = 主导分 - 次高分（0-1）；越低代表风格越混合/不明显",
    )


class ReadinessItem(CamelModel):
    """学习准备度自陈量表单项（likert 1-5）"""
    key: str = Field(..., description="题项标识，如 motivation_1 / metacognition_1 / efficacy_1")
    value: int = Field(..., ge=1, le=5, description="likert 自评 1-5")


class LearningReadinessRequest(CamelModel):
    """学习准备度提交请求（轻量自陈，5-8 题）"""
    subject: str = Field(default="人工智能导论", description="学科")
    items: List[ReadinessItem] = Field(..., min_length=1, description="自陈题项列表")


class ReadinessProfile(CamelModel):
    """学习准备度画像（第三维自变量，0-1 归一化）"""
    motivation: float = Field(default=0.0, ge=0.0, le=1.0, description="学习动机")
    metacognition: float = Field(default=0.0, ge=0.0, le=1.0, description="元认知水平")
    self_efficacy: float = Field(default=0.0, ge=0.0, le=1.0, description="自我效能感")
    raw_items: Optional[List[ReadinessItem]] = Field(
        default=None, description="原始自陈题项，便于追溯"
    )
    # 条目9: 学科特异性自我效能（锚定到具体薄弱知识点）；key=知识点ID
    efficacy_by_kp: Optional[Dict[str, float]] = Field(
        default=None, description="学科特异性自我效能 {kp_id: 0-1}；与维度一薄弱点对照形成高风险信号"
    )
    # 条目8: 纵向追踪（与上一次测绘对比的变化量）
    trend: Optional[Dict[str, float]] = Field(
        default=None, description="准备度纵向变化 {motivation, metacognition, self_efficacy}（本次-上次，可正可负）"
    )


# ═══════════ 测绘结果 ═══════════

class MasteryItem(CamelModel):
    """单个知识点的掌握度"""
    knowledge_point: str = Field(..., description="知识点名称")
    kp_id: str = Field(default="", description="知识点 ID")
    mastery: float = Field(..., ge=0.0, le=1.0, description="掌握度 0-1（点估计）")
    level: str = Field(default="developing", description="等级: weak/developing/proficient/excellent")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="置信度 0-1")
    # 条目1: 掌握度置信区间 [下界, 上界]（基于题量与正确率的经验区间）；题量过低时区间宽
    confidence_interval: Optional[List[float]] = Field(
        default=None, description="掌握度 95% 经验置信区间 [low, high]；题量不足时区间较宽"
    )
    n_questions: int = Field(default=0, ge=0, description="该知识点本次作答题数（用于判断样本充分性）")


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


class CehuiResultResponse(CamelModel):
    """测绘结果完整响应"""
    id: str = Field(..., description="测绘记录 ID")
    user_id: str = Field(..., description="用户 ID")
    created_at: datetime = Field(..., description="创建时间")
    subject: str = Field(default="", description="学科")
    grade: str = Field(default="", description="年级")

    mastery_levels: List[MasteryItem] = Field(default_factory=list, description="知识点掌握度列表")
    cognitive_load: CognitiveLoadProfile = Field(
        default_factory=CognitiveLoadProfile, description="认知负荷分析"
    )
    learning_style: Optional["LearningStyleProfile"] = Field(
        default=None, description="学习风格画像（建议 4）；为空表示未评估"
    )
    # 兼容旧前端：保留 str 标签字段（取 learning_style.label 或原 record.learning_style）
    learning_style_label: str = Field(default="未评估", description="学习风格标签（向后兼容 str 字段）")
    readiness_profile: Optional["ReadinessProfile"] = Field(
        default=None, description="学习准备度画像（第三维，可选；为空表示二维模式）"
    )
    weak_points: List[WeakPoint] = Field(default_factory=list, description="薄弱点列表")
    overall_score: float = Field(default=0.0, description="综合评分 0-100")
    summary: str = Field(default="", description="AI 测绘摘要")
    radar_data: List[RadarPoint] = Field(default_factory=list, description="雷达图数据")
    cognitive_load_index: float = Field(default=0.0, description="认知负荷指数")
    # 条目10: 跨维度交叉测绘洞察（2-3 条自然语言信号）
    cross_insights: List[str] = Field(
        default_factory=list, description="跨维度交叉测绘洞察（如'维度一X低 + 维度三X效能低 = 高风险卡点'）"
    )
    # 条目11: 量表语义说明（区分"实测掌握"与"自陈倾向"）
    scale_note: str = Field(
        default="",
        description="量表语义说明：维度一为客观答题估计的掌握度；维度二、三为自陈量表自评倾向，量纲不同不可直接比较",
    )
    # 条目14: AI 综合测绘小结（结合三维度 + 交叉信号的自然语言文案）
    ai_summary: str = Field(default="", description="AI 综合测绘小结（结合三维度与交叉信号的总结）")


class RawCehuiResult(CamelModel):
    """原始测绘结果 (简化结构，兼容旧 API)"""
    mastery_levels: dict = Field(default_factory=dict, description="{kp_id: value}")
    cognitive_load: float = Field(default=0.0, description="综合认知负荷")
    weak_points: List[str] = Field(default_factory=list, description="薄弱知识点 ID 列表")
    diagnosis_id: str = Field(default="", description="测绘记录 ID")
    radar_data: dict = Field(default_factory=dict, description="{维度名: 值}")


# ═══════════ 测绘历史 ═══════════

class CehuiBrief(CamelModel):
    """测绘历史简要条目"""
    id: str = Field(..., description="测绘记录 ID")
    created_at: datetime = Field(..., description="创建时间")
    subject: str = Field(default="", description="学科")
    overall_score: float = Field(default=0.0, description="综合评分")
    weak_point_count: int = Field(default=0, description="薄弱点数量")


class CehuiHistoryResponse(CamelModel):
    """测绘历史列表响应"""
    items: List[CehuiBrief] = Field(default_factory=list)
    total: int = Field(default=0)
