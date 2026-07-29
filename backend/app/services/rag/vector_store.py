"""向量存储 — ChromaDB 持久化向量数据库"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 延迟导入
try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False


@dataclass
class SearchHit:
    """检索命中结果"""

    chunk_id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


class VectorStoreConfig:
    """向量库配置"""

    def __init__(
        self,
        persist_directory: str = "./data/chroma_db",
        collection_name: str = "knowledge_base",
        distance_metric: str = "cosine",
    ):
        """
        Args:
            persist_directory: 持久化存储目录
            collection_name: 集合名称
            distance_metric: 距离度量方式 (cosine / l2 / ip)
        """
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.distance_metric = distance_metric


class VectorStore:
    """ChromaDB 向量存储封装"""

    def __init__(self, config: VectorStoreConfig):
        if not HAS_CHROMA:
            raise ImportError(
                "ChromaDB 未安装，请运行: pip install chromadb\n"
                "或: poetry add chromadb"
            )

        self.config = config
        self._client: Optional[chromadb.PersistentClient] = None
        self._collection: Optional[Any] = None  # chromadb Collection

        logger.info(
            "VectorStore init | dir=%s | collection=%s | metric=%s",
            config.persist_directory,
            config.collection_name,
            config.distance_metric,
        )

    @property
    def is_initialized(self) -> bool:
        return self._collection is not None

    def initialize(self) -> None:
        """初始化向量库（创建/加载持久化存储）"""
        persist_path = Path(self.config.persist_directory)
        persist_path.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=str(persist_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        # 获取或创建 collection
        try:
            self._collection = self._client.get_collection(
                name=self.config.collection_name,
            )
            logger.info(
                "Loaded existing collection '%s' | count=%d",
                self.config.collection_name,
                self._collection.count(),
            )
        except Exception:
            self._collection = self._client.create_collection(
                name=self.config.collection_name,
                metadata={"hnsw:space": self.config.distance_metric},
            )
            logger.info("Created new collection '%s'", self.config.collection_name)

    def add_embeddings(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """批量添加向量和文档

        Args:
            ids: 文档 ID 列表
            embeddings: 向量列表
            documents: 原始文本列表
            metadatas: 元数据列表（可选）
        """
        if not self.is_initialized:
            raise RuntimeError("VectorStore not initialized. Call initialize() first.")

        if not ids:
            return

        self._collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

        logger.debug("Added %d vectors to collection '%s'", len(ids), self.config.collection_name)

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, Any]] = None,
    ) -> List[SearchHit]:
        """相似度检索

        Args:
            query_embedding: 查询向量
            top_k: 返回 Top-K 结果
            where: 元数据过滤条件
            where_document: 文档内容过滤条件

        Returns:
            检索结果列表，按相似度降序排列
        """
        if not self.is_initialized:
            raise RuntimeError("VectorStore not initialized. Call initialize() first.")

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            where_document=where_document,
            include=["documents", "metadatas", "distances"],
        )

        hits: List[SearchHit] = []
        if results and results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                distance = results["distances"][0][i] if results["distances"] else 1.0
                # ChromaDB 返回的是距离，转为相似度 (cosine: sim = 1 - distance)
                score = float(1.0 - distance)

                hits.append(
                    SearchHit(
                        chunk_id=chunk_id,
                        content=results["documents"][0][i] if results["documents"] else "",
                        metadata=results["metadatas"][0][i] if results["metadatas"] else {},
                        score=score,
                    )
                )

        logger.debug("Search returned %d hits (top_k=%d)", len(hits), top_k)
        return hits

    def get_collection_stats(self) -> Dict[str, Any]:
        """获取集合统计信息"""
        if not self.is_initialized:
            return {"status": "not_initialized", "count": 0}

        return {
            "name": self.config.collection_name,
            "count": self._collection.count(),
            "directory": self.config.persist_directory,
        }

    def delete_collection(self) -> None:
        """删除整个集合"""
        if self._client and self.is_initialized:
            self._client.delete_collection(self.config.collection_name)
            self._collection = None
            logger.warning("Collection '%s' deleted", self.config.collection_name)

    def count(self) -> int:
        """获取文档数量"""
        if not self.is_initialized:
            return 0
        return self._collection.count()
