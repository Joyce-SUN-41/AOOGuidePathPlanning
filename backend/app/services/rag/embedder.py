"""向量化服务 — 讯飞星火 Embedding API + BGE 本地模型回退"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

# 可选依赖检测
try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


class EmbedderConfig:
    """向量化配置"""

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        app_id: str = "",
        embedding_url: str = "https://spark-api-open.xf-yun.com/v1/embeddings",
        model: str = "text-embedding",
        dimension: int = 1536,
        batch_size: int = 16,
        max_retries: int = 3,
        timeout: float = 30.0,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.app_id = app_id
        self.embedding_url = embedding_url
        self.model = model
        self.dimension = dimension
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.timeout = timeout


class EmbeddingResult:
    """向量化结果"""

    __slots__ = ("texts", "vectors", "model", "dimension", "error")

    def __init__(
        self,
        texts: List[str],
        vectors: List[List[float]],
        model: str = "",
        dimension: int = 0,
        error: Optional[str] = None,
    ):
        self.texts = texts
        self.vectors = vectors
        self.model = model
        self.dimension = dimension
        self.error = error

    @property
    def count(self) -> int:
        return len(self.texts)


class BaseEmbedder:
    """向量化基类"""

    async def embed(self, texts: List[str]) -> EmbeddingResult:
        raise NotImplementedError

    async def embed_query(self, text: str) -> List[float]:
        """单条查询向量化"""
        result = await self.embed([text])
        return result.vectors[0] if result.vectors else []


class SparkEmbedder(BaseEmbedder):
    """讯飞星火 Embedding API 客户端

    使用讯飞星火提供的文本向量化接口（OpenAI 兼容格式）。
    认证方式：Bearer {api_key}:{api_secret}
    """

    def __init__(self, config: EmbedderConfig):
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def is_configured(self) -> bool:
        return bool(self.config.api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def embed(self, texts: List[str]) -> EmbeddingResult:
        """批量向量化文本"""
        if not texts:
            return EmbeddingResult([], [], model=self.config.model, dimension=self.config.dimension)

        if not self.is_configured:
            logger.warning("Spark Embedding API not configured, using fallback")
            return _fallback_embed(texts, self.config.dimension)

        # 分批处理
        all_vectors: List[List[float]] = []
        headers = {
            "Authorization": f"Bearer {self.config.api_key}:{self.config.api_secret}",
            "Content-Type": "application/json",
        }

        for batch_start in range(0, len(texts), self.config.batch_size):
            batch = texts[batch_start : batch_start + self.config.batch_size]
            payload = {
                "model": self.config.model,
                "input": batch,
            }

            for attempt in range(self.config.max_retries):
                try:
                    client = await self._get_client()
                    response = await client.post(
                        self.config.embedding_url,
                        headers=headers,
                        json=payload,
                    )
                    response.raise_for_status()
                    data = response.json()

                    # 解析向量（OpenAI 兼容格式）
                    embeddings = data.get("data", [])
                    for item in sorted(embeddings, key=lambda x: x.get("index", 0)):
                        vec = item.get("embedding", [])
                        if vec:
                            all_vectors.append(vec)

                    break

                except httpx.HTTPStatusError as e:
                    logger.error("Embedding API error [%d]: %s", e.response.status_code, e.response.text[:500])
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        return EmbeddingResult(
                            texts,
                            [],
                            model=self.config.model,
                            dimension=self.config.dimension,
                            error=f"API error: {e}",
                        )
                except httpx.TimeoutException:
                    logger.error("Embedding API timeout")
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        return EmbeddingResult(
                            texts, [], error="API timeout"
                        )

        logger.debug("Embedded %d texts → %d vectors (dim=%d)", len(texts), len(all_vectors), self.config.dimension)
        return EmbeddingResult(
            texts=texts,
            vectors=all_vectors,
            model=self.config.model,
            dimension=self.config.dimension,
        )


class BGEEmbedder(BaseEmbedder):
    """BGE 本地模型 Embedder（使用 sentence-transformers）

    安装依赖:
        pip install sentence-transformers
    """

    _MODEL_NAME = "BAAI/bge-small-zh-v1.5"  # 轻量中文 BGE 模型，512 维

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or self._MODEL_NAME
        self._model = None
        self._dimension = 512

    @property
    def is_configured(self) -> bool:
        return True  # BGE 可在运行时自动下载

    async def embed(self, texts: List[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult([], [], model=self.model_name, dimension=self._dimension)

        try:
            model = self._load_model()
            loop = asyncio.get_running_loop()
            # sentence-transformers encode 是同步的，在线程池中执行
            vectors = await loop.run_in_executor(
                None, lambda: model.encode(texts, normalize_embeddings=True).tolist()
            )
            return EmbeddingResult(
                texts=texts,
                vectors=vectors,
                model=self.model_name,
                dimension=self._dimension,
            )
        except Exception as e:
            logger.error("BGE embedding error: %s", e)
            return EmbeddingResult(texts, [], error=str(e))

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading BGE model: %s", self.model_name)
            self._model = SentenceTransformer(self.model_name)
            self._dimension = self._model.get_sentence_embedding_dimension()
        return self._model


class FallingBackEmbedder(BaseEmbedder):
    """带降级的 Embedder：优先 Spark API → BGE 本地 → 哈希模拟"""

    def __init__(self, config: EmbedderConfig):
        self.spark = SparkEmbedder(config)
        self._bge: Optional[BGEEmbedder] = None

    async def embed(self, texts: List[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult([], [])

        # 优先：Spark API
        if self.spark.is_configured:
            result = await self.spark.embed(texts)
            if not result.error and result.vectors:
                return result
            logger.warning("Spark embedding failed: %s, trying BGE fallback", result.error)

        # 次选：BGE 本地
        bge = await self._get_bge()
        if bge:
            result = await bge.embed(texts)
            if not result.error and result.vectors:
                return result
            logger.warning("BGE embedding failed: %s, using hash fallback", result.error)

        # 最终降级：确定性哈希向量
        logger.warning("All embedders unavailable, using deterministic hash vectors")
        return _fallback_embed(texts, self.spark.config.dimension)

    async def embed_query(self, text: str) -> List[float]:
        result = await self.embed([text])
        return result.vectors[0] if result.vectors else []

    async def _get_bge(self) -> Optional[BGEEmbedder]:
        if self._bge:
            return self._bge
        try:
            self._bge = BGEEmbedder()
            return self._bge
        except ImportError:
            logger.warning("sentence-transformers not installed, BGE not available")
            return None

    async def close(self) -> None:
        await self.spark.close()


def _fallback_embed(texts: List[str], dimension: int = 1536) -> EmbeddingResult:
    """确定性哈希向量 — 当所有 embedding 服务不可用时的最终降级"""
    if not HAS_NUMPY:
        # 纯 Python 实现
        vectors: List[List[float]] = []
        for text in texts:
            vec = [0.0] * dimension
            h = hashlib.sha256(text.encode("utf-8")).digest()
            for i in range(dimension):
                idx = i % len(h)
                # 归一化到 [-1, 1]
                vec[i] = (h[idx] / 127.5) - 1.0
            # L2 归一化
            norm = max(sum(v * v for v in vec) ** 0.5, 1e-10)
            vectors.append([v / norm for v in vec])
        return EmbeddingResult(texts, vectors, model="hash-fallback", dimension=dimension)
    else:
        vectors = []
        for text in texts:
            h = hashlib.sha256(text.encode("utf-8")).digest()
            seed = abs(int.from_bytes(h[:8], "big"))
            rng = np.random.RandomState(seed)
            vec = rng.randn(dimension).astype(np.float32)
            vec = vec / (np.linalg.norm(vec) + 1e-10)
            vectors.append(vec.tolist())
        return EmbeddingResult(texts, vectors, model="hash-fallback", dimension=dimension)
