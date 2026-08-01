"""RAG 知识库相关 Schema"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RAGQueryRequest(BaseModel):
    """RAG 问答请求"""

    question: str = Field(..., min_length=1, max_length=2000, description="用户问题")
    top_k: int = Field(default=5, ge=1, le=20, description="检索返回数量")
    temperature: float = Field(default=0.5, ge=0.0, le=2.0, description="LLM 温度")
    max_tokens: int = Field(default=1024, ge=64, le=4096, description="最大生成 token 数")
    student_id: Optional[str] = Field(default=None, description="学生 ID（可选）")
    subject: Optional[str] = Field(default=None, description="学科过滤（可选）")
    skip_retrieval: bool = Field(default=False, description="跳过知识库检索，直接使用大模型回答")
    stream: bool = Field(
        default=False,
        description="是否以 SSE (text/event-stream) 流式返回。默认 False 保持整包 JSON 响应",
    )


class RAGSource(BaseModel):
    """问答来源"""

    document: str = Field(..., description="文档名称")
    page: str = Field(default="", description="页码")
    section: str = Field(default="", description="章节")
    content: str = Field(default="", description="引用内容摘要")
    score: float = Field(default=0.0, description="相似度得分")
    ref: int = Field(default=0, description="引用编号")


class RAGTokenUsage(BaseModel):
    """Token 用量"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class RAGQueryResponse(BaseModel):
    """RAG 问答响应"""

    answer: str = Field(..., description="AI 生成的答案")
    sources: List[RAGSource] = Field(default_factory=list, description="引用来源列表")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="置信度")
    retrieval_count: int = Field(default=0, description="检索到的文档块数量")
    model: str = Field(default="", description="使用的模型")
    token_usage: Optional[RAGTokenUsage] = Field(default=None, description="Token 用量")
    query_id: str = Field(default="", description="查询追踪 ID")


class RAGIndexRequest(BaseModel):
    """索引请求"""

    directory: str = Field(..., description="要索引的文档目录路径")
    recursive: bool = Field(default=True, description="是否递归子目录")
    clear_existing: bool = Field(default=False, description="是否先清空已有索引")


class RAGIndexResponse(BaseModel):
    """索引响应"""

    message: str = Field(..., description="结果消息")
    chunks_indexed: int = Field(default=0, description="索引的文档块数量")
    directory: str = Field(default="", description="索引的目录")


class RAGStatsResponse(BaseModel):
    """知识库统计"""

    status: str = Field(default="not_initialized", description="状态")
    documents: int = Field(default=0, description="文档数量")
    name: str = Field(default="", description="集合名称")
    directory: str = Field(default="", description="持久化目录")
    similarity_threshold: float = Field(default=0.5, description="相似度阈值")
    chunk_config: Dict[str, Any] = Field(default_factory=dict, description="分块配置")
