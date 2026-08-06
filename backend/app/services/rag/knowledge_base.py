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
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from app.core.config import settings
from app.services.llm.spark_client import ChatResponse, SparkClient
from app.services.rag.chunker import Chunk, ChunkConfig, DocumentChunker, MarkdownChunker
from app.services.rag.document_loader import DocumentLoader, LoadedDocument
from app.services.rag.embedder import EmbedderConfig, FallingBackEmbedder
from app.services.rag.vector_store import SearchHit, VectorStore, VectorStoreConfig

logger = logging.getLogger(__name__)

# 单次 LLM 调用的最大等待时间（秒）。
# 必须显著小于前端 axios 的 120s 超时，
# 这样超时可以在后端被捕获并转成可读提示，
# 而不是让浏览器抛出 "timeout of 120000ms exceeded"。
LLM_CALL_TIMEOUT: float = 90.0


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
        "你是一个采用苏格拉底式（启发式）教学法的学科辅导助手，名为“动麦智导”。\n"
        "你的核心目标不是直接把答案告诉学习者，而是通过层层追问，引导学习者自己思考、\n"
        "回忆已有知识、发现知识之间的联系，最终由学习者自己得出结论。\n\n"
        "你的行为准则：\n"
        "1. 优先基于下方参考文档中的内容作为你引导的依据，但不要整段复述文档。\n"
        "2. 先用一个简短的澄清或回应为学习者搭建台阶，然后用 1-3 个递进式问题引导其思考，\n"
        "   问题要从学习者已知处出发，逐步逼近核心概念。\n"
        "3. 当学习者已经给出正确思路时，给予肯定并引导其归纳总结；只有当学习者明显卡住、\n"
        "   或反复尝试仍无法推进时，才给出关键提示，提示仍要尽量以问题或线索形式呈现。\n"
        "4. 不要一次性给出完整的最终答案；把「得出结论的成就感」留给学习者。\n"
        "5. 语言准确、专业、温暖，适合学习者理解；可在回答末尾用一两句话点明可参考的来源编号。"
    )

    USER_PROMPT_TEMPLATE = """请以下方参考文档为依据，用苏格拉底式（启发式）方法引导学习者思考，而不是直接给出答案。

## 参考文档
{context}

## 用户问题
{question}

## 引导要求
- 基于文档内容设计引导，引用依据时标注来源编号
- 先共情/确认学习者的起点，再用 1-3 个递进问题引导其推理
- 不直接输出完整结论；把归纳总结的机会留给学习者
- 若学习者已接近正确思路，给予肯定并引导其自己收口
- 保持鼓励、清晰的语气，最后可提示"可参考来源编号"以方便延伸阅读"""

    # 直接对话（无 RAG 命中 / 非测绘）分支的系统提示：同样采用苏格拉底式，
    # 保证「导学终端」全局一致地引导而非直接给答案；品牌同步为「动麦智导」。
    DIRECT_CHAT_SOCRATIC_PROMPT = (
        "你是一个采用苏格拉底式（启发式）教学法的学科辅导助手，名为「动麦智导」。\n"
        "你的目标不是直接把答案告诉学习者，而是通过层层追问引导其自己思考、\n"
        "回忆已有知识、发现知识之间的联系，最终由学习者自己得出结论。\n"
        "1. 先用简短澄清或回应为学习者搭建台阶；\n"
        "2. 再用 1-3 个递进式问题引导其推理，问题从已知处出发逐步逼近核心；\n"
        "3. 学习者给出正确思路时给予肯定并引导其归纳总结；只有当其明显卡住时，\n"
        "   才给出关键提示，且提示仍以问题或线索形式呈现；\n"
        "4. 不要一次性给出完整最终答案；把「得出结论的成就感」留给学习者；\n"
        "5. 若问题超出知识范围，请如实说明，并可引导其思考可查证的途径。"
    )

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

    @staticmethod
    def normalize_roles(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """将 system 角色消息降级为 user 消息（部分模型不支持 system 角色）

        讯飞 generalv3 (Pro) / MaaS 部署模型对 system role 支持有限，
        将其内容合并到首条 user 消息前可避免 400 错误。
        """
        out: List[Dict[str, str]] = []
        for m in messages:
            if m.get("role") == "system":
                # 合并到前一条 user，或作为新的 user 插入
                if out and out[-1].get("role") == "user":
                    out[-1] = {
                        "role": "user",
                        "content": f"{m['content']}\n\n{m['content']}",
                    }
                else:
                    out.append({"role": "user", "content": m["content"]})
            else:
                out.append(m)
        return out


# ============================================================================
# 知识库核心服务
# ============================================================================


class KnowledgeBase:
    """RAG 知识库核心服务

    完整管线:
    1. 文档加载 (PDF/TXT/MD)
    2. 文档分块 (递归字符分割 + Markdown 标题感知)
    3. 向量化 (Spark API → BGE → 哈希降级)
    4. 向量存储 (NumPy + JSON 持久化)
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

    @property
    def vector_store(self) -> VectorStore:
        """公开向量存储实例，供外部检查文档数量"""
        if not self._vector_store:
            raise RuntimeError("VectorStore not initialized")
        return self._vector_store

    async def initialize(self) -> None:
        """初始化所有子组件"""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            logger.info("Initializing KnowledgeBase...")

            # LLM Client —— 优先创建，直连问答不依赖检索组件
            self._llm_client = SparkClient(
                api_key=settings.XF_API_KEY,
                api_secret=settings.XF_API_SECRET,
                app_id=settings.XF_APP_ID,
                api_url=settings.XF_API_URL,
                api_password=settings.XF_API_PASSWORD,
                model=settings.XF_MODEL,
            )

            # Embedder（检索增强用，失败不阻塞直连问答）
            try:
                embedder_config = EmbedderConfig(
                    api_key=settings.XF_API_KEY,
                    api_secret=settings.XF_API_SECRET,
                    app_id=settings.XF_APP_ID,
                )
                self._embedder = FallingBackEmbedder(embedder_config)
            except Exception as e:  # noqa: BLE001
                logger.warning("Embedder init skipped (直连问答不受影响): %s", e)
                self._embedder = None

            # Vector Store (NumPy + JSON, 无外部依赖)
            try:
                self._vector_store = VectorStore(self.vector_config)
                self._vector_store.initialize()
            except Exception as e:  # noqa: BLE001
                logger.warning("VectorStore init skipped (检索不可用): %s", e)
                self._vector_store = None

            self._initialized = True
            logger.info(
                "KnowledgeBase initialized | llm=%s | embedder=%s | vector=%s",
                bool(self._llm_client),
                bool(self._embedder),
                bool(self._vector_store),
            )

            # 预热嵌入器（仅当可用时）：主动触发一次空文本向量化，
            # 使 Spark/BGE 的"不可用"短路标志在初始化阶段就确立，
            # 避免首条真实 query 卡在网络超时。失败不影响直连问答。
            if self._embedder is not None:
                try:
                    await self._embedder.embed(["__warmup__"])
                except Exception as e:  # noqa: BLE001
                    logger.debug("Embedder warmup skipped: %s", e)

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

    # ---- 直连 LLM（跳过知识库检索） ----

    # 快速模式系统提示词（精简短小，尽量一次返回）
    DIRECT_CHAT_FAST_PROMPT: str = (
        "你是「动麦智导」的智能学习助手。请简洁直接地回答用户问题，"
        "控制在 200 字以内，不需要铺垫。专注学习路径规划、知识薄弱点分析、"
        "学习策略推荐。若问题超出范围，直接说明无法回答。"
    )

    # 测绘模式系统提示词（苏格拉底式引导 + 隐式评估 + JSON 输出）
    # 说明：导学终端默认走此分支（前端固定 cehui_mode=true）。
    # 早期版本此处是「直接给答案 + JSON」，导致苏格拉底式引导形同虚设（用户反馈“和原来一样”）。
    # 现改为：以苏格拉底式（启发式）层层追问进行引导，不直接抛出完整答案；
    # 同时在末尾追加学情测绘 JSON 供后端解析，从而「引导式教学」与「对话画像/路径自动优化」并存。
    DIRECT_CHAT_DIAGNOSE_PROMPT: str = (
        "你是采用苏格拉底式（启发式）教学法的学科辅导助手「动麦智导」。\n"
        "你的目标不是把答案直接告诉学习者，而是通过层层追问，引导其自己思考、回忆已有知识、\n"
        "发现知识之间的联系，最终由学习者自己得出结论；同时你要在回答中完成一次隐式学情评估。\n\n"
        "引导准则：\n"
        "1. 先用简短澄清或回应为学习者搭建台阶，再用 1-3 个递进式问题引导其推理，\n"
        "   问题从学习者已知处出发，逐步逼近核心概念；\n"
        "2. 当学习者给出正确思路时给予肯定并引导其归纳总结；只有当其明显卡住、反复尝试仍无法推进时，\n"
        "   才给出关键提示，且提示仍以问题或线索形式呈现，不要一次性给出完整最终答案；\n"
        "3. 语言准确、专业、温暖，适合学习者理解；可在引导末尾用一两句话点明可参考的方向。\n"
        "4. 当你给出的引导包含可直接照做的分步提纲、关键公式或要点列表等可复用素材时，"
        "在该段开头标注「[可复用素材]」，并在末尾用 1-3 个递进问题引导其反思，"
        "不直接把完整推导或最终答案写全，把归纳总结的机会留给学习者。\n\n"
        "学情评估（不可见，仅供后端解析）：在回答之后，必须附加一份学情测绘 JSON，\n"
        "用 [*DIAG_START*] 和 [*DIAG_END*] 包裹，用户不会看到这段 JSON：\n"
        "[*DIAG_START*]\n"
        '{"mastery_estimates":[{"kp_name":"知识点名","level":0.0-1.0}],'
        '"cognitive_load":0.0-1.0,'
        '"learning_intent":"skill_improve|basic_review|deep_dive|quick_fix",'
        '"needs_optimization":true|false}\n'
        "[*DIAG_END*]\n\n"
        "评估规则：\n"
        "- mastery_estimates: 仅评估对话中明确涉及的知识点掌握度（0=完全不会，1=精通），勿编造\n"
        "- cognitive_load: 用户表现出的认知负荷（越高=越吃力/困惑）\n"
        "- learning_intent: skill_improve(技能提升)/basic_review(基础回顾)/deep_dive(深入钻研)/quick_fix(快速答疑)\n"
        "- needs_optimization: 当检测到 2+ 薄弱知识点或用户明确要求优化路径时设为 true\n\n"
        "重要：引导正文面向学习者；测绘 JSON 紧随其后且被标记包裹，用户不应看到它，它仅供后端解析使用。"
    )

    @staticmethod
    def _extract_cehui_json(content: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        """从 LLM 回复中提取测绘 JSON 块，返回 (干净回答, 测绘数据或 None)"""
        import re

        diag_match = re.search(
            r"\[\*DIAG_START\*\](.*?)\[\*DIAG_END\*\]",
            content,
            re.DOTALL,
        )
        if not diag_match:
            return content, None

        # 移除测绘块，仅保留干净回答
        clean_answer = content[: diag_match.start()].strip() + content[diag_match.end() :].strip()
        clean_answer = clean_answer.strip()

        try:
            diag_data = json.loads(diag_match.group(1).strip())
        except json.JSONDecodeError:
            logger.warning("[direct_chat] 测绘 JSON 解析失败，丢弃")
            return clean_answer, None

        return clean_answer, diag_data

    async def direct_chat(
        self,
        question: str,
        temperature: float = 0.5,
        max_tokens: int = 1024,
        fast: bool = False,
        cehui: bool = False,
    ) -> RAGQueryResult:
        """直接调用大模型回答，不经过检索增强"""
        if not self._llm_client:
            raise RuntimeError("LLM 客户端未初始化，无法直连问答")

        query_id = str(uuid.uuid4())[:8]

        # 选择系统提示词与参数
        if cehui:
            system_prompt = self.DIRECT_CHAT_DIAGNOSE_PROMPT
            _temperature = min(temperature, 0.35)  # 测绘即快速
            _max_tokens = min(max_tokens, fast and 512 or 640)
            _timeout = min(LLM_CALL_TIMEOUT, fast and 30.0 or 45.0)
        elif fast:
            system_prompt = self.DIRECT_CHAT_FAST_PROMPT
            _temperature = min(temperature, 0.35)
            _max_tokens = min(max_tokens, 384)
            _timeout = min(LLM_CALL_TIMEOUT, 30.0)
        else:
            system_prompt = self.DIRECT_CHAT_SOCRATIC_PROMPT
            _temperature = temperature
            _max_tokens = max_tokens
            _timeout = LLM_CALL_TIMEOUT

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ]
        messages = RAGPromptBuilder.normalize_roles(messages)

        mode_tag = "fast" if fast else ("cehui" if cehui else "normal")
        logger.info(
            "[direct_chat] 直连 LLM | mode=%s | id=%s | q=%s",
            mode_tag, query_id, question[:60],
        )

        # 预检：LLM 客户端是否已配置
        if not self._llm_client.is_configured:
            msg = (
                "LLM 服务未配置，请检查环境变量: "
                "REST 模式需 XF_API_URL + XF_API_PASSWORD；"
                "WebSocket 模式需 XF_APP_ID + XF_API_KEY + XF_API_SECRET + XF_ASSISTANT_ID"
            )
            logger.warning("[direct_chat] %s", msg)
            return RAGQueryResult(
                answer=f"AI 服务未配置：{msg}",
                sources=[],
                confidence=0.0,
                retrieval_count=0,
                model=self._llm_client.model or "",
                query_id=query_id,
            )

        try:
            response = await asyncio.wait_for(
                self._llm_client.chat(
                    messages=messages,
                    temperature=_temperature,
                    max_tokens=_max_tokens,
                ),
                timeout=_timeout,
            )
        except asyncio.TimeoutError:
            logger.error("[direct_chat] LLM 调用超时 (%.0fs)", _timeout)
            return RAGQueryResult(
                answer=(
                    f"AI 生成超时（超过 {_timeout:.0f} 秒）。"
                    "可能是模型服务繁忙，请稍后重试或缩短问题长度。"
                ),
                sources=[],
                confidence=0.0,
                retrieval_count=0,
                model=self._llm_client.model or "",
                query_id=query_id,
            )
        except Exception as e:
            logger.error("[direct_chat] LLM 调用失败: %s", e)
            return RAGQueryResult(
                answer=f"AI 服务暂时不可用: {e}",
                sources=[],
                confidence=0.0,
                retrieval_count=0,
                model=self._llm_client.model or "",
                query_id=query_id,
            )

        token_usage = None
        if response.usage:
            token_usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        # 测绘模式：提取测绘 JSON
        answer_text = response.content
        cehui = None
        if cehui:
            answer_text, cehui = self._extract_cehui_json(answer_text)

        result = RAGQueryResult(
            answer=answer_text,
            sources=[],
            confidence=0.7,
            retrieval_count=0,
            model=self._llm_client.model or "",
            token_usage=token_usage,
            query_id=query_id,
        )

        # 附加测绘数据到 result（通过私有属性）
        if cehui is not None:
            result._cehui = cehui  # type: ignore[attr-defined]

        return result

    async def direct_chat_stream(
        self,
        question: str,
        temperature: float = 0.5,
        max_tokens: int = 1024,
        fast: bool = False,
        cehui: bool = False,
    ) -> AsyncGenerator[str, None]:
        """直连大模型的流式问答（不经过检索增强）

        与 direct_chat 使用相同的 system prompt，仅输出方式改为逐块。

        Yields:
            增量答案文本；结束前产出一条 "<<SOURCES>>[]" 标记以对齐 query_stream 协议
        """
        if not self._llm_client:
            yield "AI 服务未初始化，请稍后重试。"
            yield "<<SOURCES>>" + json.dumps([], ensure_ascii=False)
            return

        if not self._llm_client.is_configured:
            yield (
                "AI 服务未配置，请检查环境变量: "
                "REST 模式需 XF_API_URL + XF_API_PASSWORD；"
                "WebSocket 模式需 XF_APP_ID + XF_API_KEY + XF_API_SECRET + XF_ASSISTANT_ID"
            )
            yield "<<SOURCES>>" + json.dumps([], ensure_ascii=False)
            return

        # 选择系统提示词与参数
        if cehui:
            system_prompt = self.DIRECT_CHAT_DIAGNOSE_PROMPT
            _temperature = min(temperature, 0.35)
            _max_tokens = min(max_tokens, fast and 512 or 640)
        elif fast:
            system_prompt = self.DIRECT_CHAT_FAST_PROMPT
            _temperature = min(temperature, 0.35)
            _max_tokens = min(max_tokens, 384)
        else:
            system_prompt = self.DIRECT_CHAT_SOCRATIC_PROMPT
            _temperature = temperature
            _max_tokens = max_tokens

        messages = RAGPromptBuilder.normalize_roles(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ]
        )

        full_content = ""
        # 测绘模式：用状态机过滤测绘 JSON 块，避免暴露给用户
        _diag_buf = ""          # 滑窗缓冲区，用于跨 chunk 检测标记
        _in_diag_block = False  # 是否已进入 [*DIAG_START*] 区间
        _diag_json = ""         # 累积的测绘 JSON 内容
        _DIAG_START = "[*DIAG_START*]"
        _DIAG_END = "[*DIAG_END*]"
        try:
            async for chunk in self._llm_client.chat_stream(
                messages=messages,
                temperature=_temperature,
                max_tokens=_max_tokens,
            ):
                if not chunk.content:
                    continue
                full_content += chunk.content

                if not cehui:
                    yield chunk.content
                    continue

                # ── 测绘模式：过滤 [*DIAG_START*]...[*DIAG_END*] 块 ──
                _diag_buf += chunk.content

                if not _in_diag_block:
                    # 未进入测绘块：查找 [*DIAG_START*]
                    idx = _diag_buf.find(_DIAG_START)
                    if idx >= 0:
                        # 找到开始标记：先产出标记之前的正常内容
                        before = _diag_buf[:idx]
                        if before:
                            yield before
                        # 切除已处理部分，含标记本身
                        _diag_buf = _diag_buf[idx + len(_DIAG_START):]
                        _in_diag_block = True
                    else:
                        # 没找到：保留尾部可能跨 chunk 的片段，其余安全产出
                        tail_len = len(_DIAG_START) - 1
                        if len(_diag_buf) > tail_len:
                            safe = _diag_buf[:-tail_len]
                            yield safe
                            _diag_buf = _diag_buf[-tail_len:]
                else:
                    # 已在测绘块内：查找 [*DIAG_END*]
                    idx = _diag_buf.find(_DIAG_END)
                    if idx >= 0:
                        # 测绘块结束：收集到测绘 JSON
                        _diag_json = _diag_buf[:idx]
                        # 切除测绘块 + 结束标记
                        _diag_buf = _diag_buf[idx + len(_DIAG_END):]
                        _in_diag_block = False
                    else:
                        # 仍在测绘块中，保留尾部等待结束标记
                        tail_len = len(_DIAG_END) - 1
                        if len(_diag_buf) > tail_len:
                            _diag_json += _diag_buf[:-tail_len]
                            _diag_buf = _diag_buf[-tail_len:]

        except Exception as e:  # noqa: BLE001
            logger.error("[direct_chat_stream] LLM 流式调用失败: %s", e)
            yield "\n\n[AI 生成过程中出现错误，请重试]"
            return

        # 测绘块结束后可能还有残留正常内容
        if _diag_buf and not _in_diag_block:
            yield _diag_buf
        # 如果仍在测绘块中（异常/未闭合），不产出，直接丢弃

        # 测绘模式：将解析结果作为结构化 SSE 帧发送
        if cehui and _diag_json:
            try:
                cehui = json.loads(_diag_json.strip())
                yield "<<CEHUI>>" + json.dumps(cehui, ensure_ascii=False)
            except json.JSONDecodeError:
                logger.warning("[direct_chat_stream] 测绘 JSON 解析失败，丢弃")

        yield "<<SOURCES>>" + json.dumps([], ensure_ascii=False)

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
        # 部分模型不支持 system 角色，降级为 user
        messages = RAGPromptBuilder.normalize_roles(messages)

        # Step 3: LLM 生成
        if not self._llm_client.is_configured:
            msg = (
                "LLM 服务未配置，请检查环境变量: "
                "REST 模式需 XF_API_URL + XF_API_PASSWORD；"
                "WebSocket 模式需 XF_APP_ID + XF_API_KEY + XF_API_SECRET + XF_ASSISTANT_ID"
            )
            logger.warning("[RAG query] %s", msg)
            return RAGQueryResult(
                answer=f"AI 服务未配置：{msg}",
                sources=sources,
                confidence=0.0,
                retrieval_count=retrieval.count,
                query_id=query_id,
            )

        try:
            # 必须设置超时上限：前端 axios 在 120s 处硬性中断，
            # 若后端一直挂着等待 LLM，用户只会看到无意义的
            # "timeout of 120000ms exceeded"。这里提前失败并给出可读原因。
            response = await asyncio.wait_for(
                self._llm_client.chat(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
                timeout=LLM_CALL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error("LLM call timed out after %.0fs in RAG query", LLM_CALL_TIMEOUT)
            return RAGQueryResult(
                answer=(
                    f"AI 生成超时（超过 {LLM_CALL_TIMEOUT:.0f} 秒）。"
                    "可能是模型服务繁忙，请稍后重试或缩短问题长度。"
                ),
                sources=sources,
                confidence=0.0,
                retrieval_count=retrieval.count,
                query_id=query_id,
            )
        except Exception as e:
            logger.error("LLM call failed in RAG query: %s", e)
            return RAGQueryResult(
                answer=f"AI 服务暂时不可用: {e}",
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
        try:
            await _knowledge_base_instance.initialize()
        except Exception:
            # 初始化失败时重置，让下次请求可以重试
            _knowledge_base_instance = None
            raise

    return _knowledge_base_instance


async def reset_knowledge_base() -> None:
    """重置知识库（用于配置变更后重建）"""
    global _knowledge_base_instance
    if _knowledge_base_instance is not None:
        await _knowledge_base_instance.close()
        _knowledge_base_instance = None
        logger.info("KnowledgeBase global singleton reset")
