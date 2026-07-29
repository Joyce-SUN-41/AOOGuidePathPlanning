"""知识库服务 — RAG 完整流程编排

管线: 文档加载 → 分块 → 向量化 → 存储 → 检索 → 问答生成
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from app.core.config import settings
from app.services.llm.spark_client import ChatResponse, SparkClient
from app.services.rag.chunker import Chunk, ChunkConfig, DocumentChunker, MarkdownChunker
from app.services.rag.document_loader import DocumentLoader, LoadedDocument
from app.services.rag.embedder import EmbedderConfig, FallingBackEmbedder
from app.services.rag.vector_store import SearchHit, VectorStore, VectorStoreConfig

logger = logging.getLogger(__name__)


# ============================================================================
# 数据模型
# ============================================================================


@dataclass
class RAGQueryResult:
    """RAG 问答结果"""

    answer: str = ""
    sources: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    retrieval_count: int = 0
    model: str = ""
    token_usage: Optional[Dict[str, int]] = None
    query_id: str = ""


@dataclass
class RetrievalResult:
    """检索结果"""

    hits: List[SearchHit]
    query: str
    elapsed_ms: float

    @property
    def count(self) -> int:
        return len(self.hits)


# ============================================================================
# RAG Prompt 模板
# ============================================================================


class RAGPromptBuilder:
    """构建 RAG 增强提示词"""

    SYSTEM_PROMPT = (
        "你是一个专业的学科知识助手，名为“燕麦智导”。\n"
        "你的任务是：\n"
        "1. 根据提供的参考文档内容回答用户问题\n"
        "2. 如果文档中有相关信息，优先基于文档回答\n"
        "3. 如果文档中没有相关信息，如实告知用户，并给出一般性回答\n"
        "4. 回答要准确、专业、清晰，适合学习者理解\n"
        "5. 在回答末尾注明信息来源"
    )

    USER_PROMPT_TEMPLATE = """请根据以下参考文档回答用户问题。

## 参考文档
{context}

## 用户问题
{question}

## 回答要求
- 基于上述文档内容回答，引用相关信息时标注来源
- 如果文档不能完全回答问题，请补充你的知识（需明确区分"文档记载"和"知识补充"）
- 使用清晰的结构，必要时使用分点或步骤说明
- 最后列出参考来源的编号"""

    @classmethod
    def build(
        cls,
        question: str,
        hits: List[SearchHit],
        max_context_chars: int = 4000,
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
        """构建 RAG 增强的 prompt 和来源列表

        Returns:
            (messages 列表, 来源信息列表)
        """
        # 构建上下文
        context_parts: List[str] = []
        sources: List[Dict[str, Any]] = []
        total_chars = 0

        for i, hit in enumerate(hits):
            source_ref = i + 1  # 引用编号从 1 开始
            chunk_text = hit.content[:1500]  # 单个块最多 1500 字

            # 检查是否超出总上下文限制
            if total_chars + len(chunk_text) > max_context_chars:
                # 截断最后一个块
                remaining = max_context_chars - total_chars
                if remaining > 200:
                    chunk_text = chunk_text[:remaining] + "..."
                else:
                    break

            context_parts.append(f"[来源{source_ref}] {chunk_text}")
            total_chars += len(chunk_text)

            sources.append({
                "document": hit.metadata.get("document", "未知文档"),
                "page": hit.metadata.get("page", ""),
                "section": hit.metadata.get("section", ""),
                "content": hit.content[:300],
                "score": round(hit.score, 4),
                "ref": source_ref,
            })

        context = "\n\n---\n\n".join(context_parts)

        return [
            {"role": "system", "content": cls.SYSTEM_PROMPT},
            {"role": "user", "content": cls.USER_PROMPT_TEMPLATE.format(
                context=context,
                question=question,
            )},
        ], sources

    @classmethod
    def build_stream(
        cls,
        question: str,
        hits: List[SearchHit],
        max_context_chars: int = 4000,
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
        """同 build，但 messages 不含 system（stream 模式兼容）"""
        return cls.build(question, hits, max_context_chars)


# ============================================================================
# 知识库核心服务
# ============================================================================


class KnowledgeBase:
    """RAG 知识库核心服务

    完整管线:
    1. 文档加载 (PDF/TXT/MD)
    2. 文档分块 (递归字符分割 + Markdown 标题感知)
    3. 向量化 (Spark API → BGE → 哈希降级)
    4. 向量存储 (ChromaDB 持久化)
    5. 语义检索 (Top-K + 相似度阈值)
    6. RAG 问答 (检索 → 构建 Prompt → LLM 生成)

    用法:
        kb = KnowledgeBase()
        await kb.initialize()

        # 索引文档
        count = await kb.index_directory("./docs/subjects/")

        # 问答
        result = await kb.query("什么是归一化？", top_k=5)

        # 流式问答
        async for chunk in kb.query_stream("什么是梯度下降？"):
            print(chunk, end="")
    """

    def __init__(
        self,
        chunk_config: Optional[ChunkConfig] = None,
        persist_directory: Optional[str] = None,
        collection_name: str = "knowledge_base",
        similarity_threshold: float = 0.5,
    ):
        self.similarity_threshold = similarity_threshold

        # 子组件
        self.chunk_config = chunk_config or ChunkConfig()
        self.vector_config = VectorStoreConfig(
            persist_directory=persist_directory or settings.RAG_PERSIST_DIR,
            collection_name=collection_name,
        )

        self._embedder: Optional[FallingBackEmbedder] = None
        self._vector_store: Optional[VectorStore] = None
        self._llm_client: Optional[SparkClient] = None
        self._initialized = False
        self._lock = asyncio.Lock()

    # ---- 初始化 ----

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    async def initialize(self) -> None:
        """初始化所有子组件"""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            logger.info("Initializing KnowledgeBase...")

            # Embedder
            embedder_config = EmbedderConfig(
                api_key=settings.XF_API_KEY,
                api_secret=settings.XF_API_SECRET,
                app_id=settings.XF_APP_ID,
            )
            self._embedder = FallingBackEmbedder(embedder_config)

            # Vector Store
            self._vector_store = VectorStore(self.vector_config)
            self._vector_store.initialize()

            # LLM Client
            from app.services.llm.spark_client import SparkClient

            self._llm_client = SparkClient(
                api_key=settings.XF_API_KEY,
                api_secret=settings.XF_API_SECRET,
                app_id=settings.XF_APP_ID,
                model=settings.XF_MODEL,
            )

            self._initialized = True
            logger.info("KnowledgeBase initialized | collection=%s | docs=%d",
                        self.vector_config.collection_name, self._vector_store.count())

    async def close(self) -> None:
        """释放资源"""
        if self._embedder:
            await self._embedder.close()
        if self._llm_client:
            await self._llm_client.close()
        self._initialized = False
        logger.info("KnowledgeBase closed")

    def _ensure_initialized(self):
        if not self._initialized:
            raise RuntimeError("KnowledgeBase not initialized. Call await kb.initialize() first.")

    # ---- 文档索引 ----

    async def index_directory(
        self,
        directory: str,
        *,
        recursive: bool = True,
        clear_existing: bool = False,
    ) -> int:
        """索引目录中的所有文档

        Args:
            directory: 文档目录路径
            recursive: 是否递归子目录
            clear_existing: 是否先清空已有数据

        Returns:
            索引的文档块数量
        """
        self._ensure_initialized()

        if clear_existing:
            self._vector_store.delete_collection()
            self._vector_store.initialize()
            logger.info("Cleared existing collection before re-indexing")

        logger.info("Indexing directory: %s", directory)

        # Step 1: 加载文档
        documents = DocumentLoader.load_directory(directory, recursive=recursive)
        if not documents:
            logger.warning("No documents loaded from %s", directory)
            return 0

        logger.info("Loaded %d documents, chunking...", len(documents))

        # Step 2: 分块
        all_chunks = self._chunk_documents(documents)
        logger.info("Created %d chunks from %d documents", len(all_chunks), len(documents))

        if not all_chunks:
            return 0

        # Step 3: 向量化 + 存储
        chunk_count = await self._embed_and_store(all_chunks)
        logger.info("Index complete: %d chunks stored", chunk_count)

        return chunk_count

    async def index_document(self, file_path: str) -> int:
        """索引单个文档"""
        self._ensure_initialized()

        doc = DocumentLoader.load_file(file_path)
        all_chunks = self._chunk_documents([doc])
        return await self._embed_and_store(all_chunks)

    async def index_text(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """索引纯文本"""
        self._ensure_initialized()

        chunker = DocumentChunker(self.chunk_config)
        chunks = chunker.chunk_document(content, metadata)
        return await self._embed_and_store(chunks)

    def _chunk_documents(self, documents: List[LoadedDocument]) -> List[Chunk]:
        """将文档列表分块"""
        all_chunks: List[Chunk] = []
        chunk_index = 0

        for doc in documents:
            # 选择分块器
            if doc.file_type == "md":
                chunker = MarkdownChunker(self.chunk_config)
            else:
                chunker = DocumentChunker(self.chunk_config)

            for page in doc.pages:
                meta = {
                    "document": doc.file_name,
                    "file_path": doc.file_path,
                    "file_type": doc.file_type,
                    "page": page.page_number,
                    "section": page.metadata.get("section", ""),
                    **doc.metadata,
                }
                page_chunks = chunker.chunk_document(page.text, meta)
                for ch in page_chunks:
                    ch.chunk_index = chunk_index
                    chunk_index += 1
                all_chunks.extend(page_chunks)

        return all_chunks

    async def _embed_and_store(self, chunks: List[Chunk]) -> int:
        """向量化并存储分块"""
        if not chunks:
            return 0

        batch_size = self._embedder.spark.config.batch_size
        stored = 0

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]

            # 生成 ID
            ids = [self._make_chunk_id(c) for c in batch]
            texts = [c.content for c in batch]
            metadatas = [c.metadata for c in batch]

            # 向量化
            result = await self._embedder.embed(texts)
            if result.error or not result.vectors:
                logger.error("Embedding error for batch: %s", result.error)
                continue

            # 存储
            self._vector_store.add_embeddings(
                ids=ids,
                embeddings=result.vectors,
                documents=texts,
                metadatas=metadatas,
            )
            stored += len(batch)

            logger.debug("Batch stored: %d/%d chunks", stored, len(chunks))

        return stored

    @staticmethod
    def _make_chunk_id(chunk: Chunk) -> str:
        """生成唯一的块 ID"""
        raw = f"{chunk.metadata.get('file_path', '')}:{chunk.chunk_index}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    # ---- 检索 ----

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        threshold: Optional[float] = None,
    ) -> RetrievalResult:
        """检索相关文档块

        Args:
            query: 查询文本
            top_k: 返回数量
            threshold: 相似度阈值（默认使用实例配置）

        Returns:
            检索结果
        """
        self._ensure_initialized()

        threshold = threshold if threshold is not None else self.similarity_threshold
        t0 = asyncio.get_event_loop().time()

        # 向量化查询
        query_vec = await self._embedder.embed_query(query)
        if not query_vec:
            logger.error("Failed to embed query, returning empty result")
            return RetrievalResult(hits=[], query=query, elapsed_ms=0)

        # 检索
        hits = self._vector_store.search(query_vec, top_k=top_k)

        # 相似度阈值过滤
        hits = [h for h in hits if h.score >= threshold]

        elapsed = (asyncio.get_event_loop().time() - t0) * 1000
        logger.info("Retrieve: '%s' → %d hits (%.1fms, threshold=%.2f)",
                     query[:50], len(hits), elapsed, threshold)

        return RetrievalResult(hits=hits, query=query, elapsed_ms=elapsed)

    # ---- RAG 问答 ----

    async def query(
        self,
        question: str,
        top_k: int = 5,
        temperature: float = 0.5,
        max_tokens: int = 1024,
    ) -> RAGQueryResult:
        """RAG 问答（非流式）

        流程: 检索相关文档 → 构建增强 Prompt → LLM 生成答案

        Args:
            question: 用户问题
            top_k: 检索返回数
            temperature: LLM 温度
            max_tokens: 最大生成 token 数

        Returns:
            RAGQueryResult 包含答案、来源、置信度
        """
        self._ensure_initialized()

        query_id = str(uuid.uuid4())[:8]

        # Step 1: 检索
        retrieval = await self.retrieve(question, top_k=top_k)
        if not retrieval.hits:
            return RAGQueryResult(
                answer="抱歉，我没有在知识库中找到与您问题相关的信息。请尝试换个问法或联系管理员补充相关学科资料。",
                sources=[],
                confidence=0.0,
                retrieval_count=0,
                query_id=query_id,
            )

        # Step 2: 构建 Prompt
        messages, sources = RAGPromptBuilder.build(question, retrieval.hits)

        # Step 3: LLM 生成
        try:
            response = await self._llm_client.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as e:
            logger.error("LLM call failed in RAG query: %s", e)
            return RAGQueryResult(
                answer="AI 服务暂时不可用，请稍后重试。",
                sources=sources,
                confidence=0.0,
                retrieval_count=retrieval.count,
                query_id=query_id,
            )

        # Step 4: 计算置信度
        confidence = self._calculate_confidence(retrieval.hits, response)

        token_usage = None
        if response.usage:
            token_usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        logger.info("RAG query complete | id=%s | hits=%d | confidence=%.2f",
                     query_id, retrieval.count, confidence)

        return RAGQueryResult(
            answer=response.content,
            sources=sources,
            confidence=round(confidence, 4),
            retrieval_count=retrieval.count,
            model=self._llm_client.model,
            token_usage=token_usage,
            query_id=query_id,
        )

    async def query_stream(
        self,
        question: str,
        top_k: int = 5,
        temperature: float = 0.5,
        max_tokens: int = 1024,
    ) -> AsyncGenerator[str, None]:
        """RAG 流式问答

        Yields:
            增量答案文本
        """
        self._ensure_initialized()

        # Step 1: 检索
        retrieval = await self.retrieve(question, top_k=top_k)

        if not retrieval.hits:
            yield "抱歉，我没有在知识库中找到与您问题相关的信息。请尝试换个问法。"
            yield "<<SOURCES>>" + json.dumps([], ensure_ascii=False)
            return

        # Step 2: 构建 Prompt
        messages, sources = RAGPromptBuilder.build_stream(question, retrieval.hits)

        # Step 3: LLM 流式生成
        full_answer: List[str] = []
        try:
            async for chunk in self._llm_client.chat_stream(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                if chunk.content:
                    full_answer.append(chunk.content)
                    yield chunk.content
        except Exception as e:
            logger.error("LLM stream failed in RAG query: %s", e)
            yield "\n\n[AI 生成过程中出现错误，请重试]"
            return

        # Yield 来源信息（作为特殊标记）
        yield "<<SOURCES>>" + json.dumps(sources, ensure_ascii=False)

    # ---- 置信度计算 ----

    @staticmethod
    def _calculate_confidence(hits: List[SearchHit], response: ChatResponse) -> float:
        """综合计算答案置信度

        因素:
        - 最高检索相似度 (权重 40%)
        - 平均检索相似度 (权重 30%)
        - 答案长度合理性 (权重 15%)
        - 检索结果数量 (权重 15%)
        """
        if not hits:
            return 0.0

        # 相似度因素
        max_score = max(h.score for h in hits)
        avg_score = sum(h.score for h in hits) / len(hits)

        # 长度因素 (理想答案 100~2000 字符)
        answer_len = len(response.content)
        if answer_len == 0:
            length_score = 0.0
        elif answer_len < 50:
            length_score = 0.5
        elif answer_len > 3000:
            length_score = 0.7
        else:
            length_score = 1.0

        # 检索数量因素 (2~5 个结果最佳)
        n = len(hits)
        if n >= 5:
            count_score = 1.0
        elif n >= 3:
            count_score = 0.85
        elif n >= 2:
            count_score = 0.7
        else:
            count_score = 0.5

        confidence = (
            max_score * 0.4
            + avg_score * 0.3
            + length_score * 0.15
            + count_score * 0.15
        )

        return min(max(confidence, 0.0), 1.0)

    # ---- 管理方法 ----

    def get_stats(self) -> Dict[str, Any]:
        """获取知识库状态"""
        if not self._initialized:
            return {"status": "not_initialized", "documents": 0}

        return {
            **self._vector_store.get_collection_stats(),
            "similarity_threshold": self.similarity_threshold,
            "chunk_config": {
                "chunk_size": self.chunk_config.chunk_size,
                "chunk_overlap": self.chunk_config.chunk_overlap,
                "min_chunk_size": self.chunk_config.min_chunk_size,
            },
        }


# ============================================================================
# 全局单例
# ============================================================================

_knowledge_base_instance: Optional[KnowledgeBase] = None


async def get_knowledge_base() -> KnowledgeBase:
    """获取全局 KnowledgeBase 单例（自动初始化）"""
    global _knowledge_base_instance

    if _knowledge_base_instance is None:
        _knowledge_base_instance = KnowledgeBase()
        await _knowledge_base_instance.initialize()

    return _knowledge_base_instance


async def reset_knowledge_base() -> None:
    """重置知识库（用于配置变更后重建）"""
    global _knowledge_base_instance
    if _knowledge_base_instance is not None:
        await _knowledge_base_instance.close()
        _knowledge_base_instance = None
        logger.info("KnowledgeBase global singleton reset")
