"""RAG 模块 — 检索增强生成知识库服务

核心组件:
- KnowledgeBase: 完整 RAG 管线编排
- DocumentLoader: 文档加载 (PDF/TXT/MD)
- DocumentChunker / MarkdownChunker: 文档分块
- FallingBackEmbedder: 向量化 (Spark → BGE → 哈希降级)
- VectorStore: ChromaDB 向量存储

用法:
    from app.services.rag import get_knowledge_base

    kb = await get_knowledge_base()
    result = await kb.query("什么是认知诊断？", top_k=5)
"""

from app.services.rag.chunker import Chunk, ChunkConfig, DocumentChunker, MarkdownChunker
from app.services.rag.document_loader import DocumentLoader, LoadedDocument, LoadedPage
from app.services.rag.embedder import (
    BGEEmbedder,
    EmbedderConfig,
    FallingBackEmbedder,
    SparkEmbedder,
)
from app.services.rag.knowledge_base import (
    KnowledgeBase,
    RAGQueryResult,
    RAGPromptBuilder,
    RetrievalResult,
    get_knowledge_base,
    reset_knowledge_base,
)
from app.services.rag.vector_store import SearchHit, VectorStore, VectorStoreConfig

# 保留旧版兼容
from app.services.rag.knowledge_base import KnowledgeBase as RAGService  # noqa: F401

__all__ = [
    # 核心服务
    "KnowledgeBase",
    "RAGService",
    "get_knowledge_base",
    "reset_knowledge_base",
    # 文档加载
    "DocumentLoader",
    "LoadedDocument",
    "LoadedPage",
    # 分块
    "Chunk",
    "ChunkConfig",
    "DocumentChunker",
    "MarkdownChunker",
    # 向量化
    "EmbedderConfig",
    "SparkEmbedder",
    "BGEEmbedder",
    "FallingBackEmbedder",
    # 向量存储
    "VectorStore",
    "VectorStoreConfig",
    "SearchHit",
    # 模型
    "RAGQueryResult",
    "RAGPromptBuilder",
    "RetrievalResult",
]
