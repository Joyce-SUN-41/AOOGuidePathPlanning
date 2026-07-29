"""知识点管理 & 知识图谱 Schema"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── 知识点 ────────────────────────────────────────────

class KnowledgePointCreate(BaseModel):
    """创建知识点"""
    name: str = Field(..., min_length=1, max_length=200, description="知识点名称")
    description: Optional[str] = Field(default=None, description="描述")
    subject: str = Field(..., min_length=1, max_length=100, description="学科")
    difficulty_level: int = Field(default=1, ge=1, le=5, description="难度 1-5")
    layer: Optional[str] = Field(default=None, description="层级: 基础层/核心层/进阶层")
    tags: List[str] = Field(default_factory=list, description="标签列表")
    prerequisites: List[str] = Field(default_factory=list, description="前置知识点 ID 列表")
    parent_id: Optional[str] = Field(default=None, description="父知识点 ID")


class KnowledgePointUpdate(BaseModel):
    """更新知识点"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    subject: Optional[str] = Field(default=None, min_length=1, max_length=100)
    difficulty_level: Optional[int] = Field(default=None, ge=1, le=5)
    layer: Optional[str] = None
    tags: Optional[List[str]] = None
    prerequisites: Optional[List[str]] = None
    parent_id: Optional[str] = None


class KnowledgePointOut(BaseModel):
    """知识点响应"""
    id: str
    name: str
    description: Optional[str] = None
    subject: str
    difficulty_level: int
    layer: Optional[str] = None
    tags: List[str] = []
    parent_id: Optional[str] = None
    prerequisites: List[str] = []
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class KnowledgePointBrief(BaseModel):
    """知识点简要"""
    id: str
    name: str
    subject: str
    difficulty_level: int
    layer: Optional[str] = None


# ── 知识图谱 ──────────────────────────────────────────

class KnowledgeGraphEdgeOut(BaseModel):
    """图谱边"""
    id: str
    source_kp_id: str
    source_name: str = ""
    target_kp_id: str
    target_name: str = ""
    relation_type: str = "prerequisite"

    model_config = {"from_attributes": True}


class KnowledgeGraphResponse(BaseModel):
    """完整知识图谱"""
    nodes: List[KnowledgePointOut]
    edges: List[KnowledgeGraphEdgeOut]


class KnowledgePointDetail(BaseModel):
    """知识点详情 (含前后置关系)"""
    id: str
    name: str
    description: Optional[str] = None
    subject: str
    difficulty_level: int
    layer: Optional[str] = None
    tags: List[str] = []
    prerequisites: List[KnowledgePointBrief] = []      # 前置
    dependents: List[KnowledgePointBrief] = []          # 后置 (依赖当前知识点的)
    question_count: int = 0
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── 题库题目 ──────────────────────────────────────────

class QuestionOption(BaseModel):
    """题目选项"""
    id: str
    text: str
    weight: float = 0.0


class QuestionCreate(BaseModel):
    """创建题目"""
    code: str = Field(..., description="题目编号")
    kp_ids: List[str] = Field(..., min_length=1, description="关联知识点ID")
    subject: str = Field(default="人工智能导论", description="学科")
    difficulty: int = Field(..., ge=1, le=5, description="难度")
    type: str = Field(default="single", description="题型: single | multiple")
    title: str = Field(..., description="题目文本")
    options: List[QuestionOption] = Field(..., min_length=2, max_length=6)
    correct_option_id: str = Field(..., description="正确选项ID")
    expected_time_sec: int = Field(default=20, ge=5, le=600, description="预期答题时间(秒)")
    explanation: Optional[str] = Field(default=None, description="答案解析")


class QuestionUpdate(BaseModel):
    """更新题目"""
    code: Optional[str] = None
    kp_ids: Optional[List[str]] = None
    subject: Optional[str] = None
    difficulty: Optional[int] = Field(default=None, ge=1, le=5)
    type: Optional[str] = None
    title: Optional[str] = None
    options: Optional[List[QuestionOption]] = None
    correct_option_id: Optional[str] = None
    expected_time_sec: Optional[int] = Field(default=None, ge=5, le=600)
    explanation: Optional[str] = None
    is_active: Optional[bool] = None


class QuestionOut(BaseModel):
    """题目响应"""
    id: str
    code: str
    kp_ids: List[str] = []
    kp_names: List[str] = []  # 关联知识点名称
    subject: str
    difficulty: int
    type: str
    title: str
    options: List[QuestionOption]
    correct_option_id: str
    expected_time_sec: int
    explanation: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class QuestionListResponse(BaseModel):
    """题目列表"""
    items: List[QuestionOut]
    total: int
    page: int
    page_size: int
