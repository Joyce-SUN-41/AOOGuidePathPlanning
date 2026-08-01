"""向量存储 — NumPy 内存向量 + JSON 持久化（零额外依赖，替代 ChromaDB）

设计理念：
- 内存中维护 np.ndarray 向量矩阵，写入时同步持久化到 JSON 文件
- 余弦相似度检索：存储时 L2 归一化 → 检索时 dot product = cosine
- 单 JSON 文件，原子写入（写临时文件后 rename），避免损坏
- 零外部依赖：仅用 Python 标准库 + numpy（项目中已存在）
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class SearchHit:
    """检索命中结果"""

    chunk_id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


@dataclass
class VectorStoreConfig:
    """向量库配置"""

    persist_directory: str = "./data/vector_store"
    collection_name: str = "knowledge_base"
    distance_metric: str = "cosine"

    def __post_init__(self) -> None:
        if self.distance_metric not in ("cosine", "dot"):
            raise ValueError(f"Unsupported distance_metric: {self.distance_metric}")


# ---------------------------------------------------------------------------
# 向量存储
# ---------------------------------------------------------------------------


class VectorStore:
    """NumPy 内存向量存储 + JSON 文件持久化。

    用法:
        store = VectorStore(config)
        store.initialize()
        store.add_embeddings(ids, embeddings, documents, metadatas)
        hits = store.search(query_embedding, top_k=5)
    """

    # JSON 文件内部格式版本号（用于未来兼容）
    _FORMAT_VERSION: int = 1

    def __init__(self, config: VectorStoreConfig) -> None:
        self.config = config

        # ── 内存数据结构 ──
        self._ids: List[str] = []
        self._documents: List[str] = []
        self._metadatas: List[Dict[str, Any]] = []
        self._vectors: Optional[np.ndarray] = None  # shape (N, dim)，已 L2 归一化
        self._initialized: bool = False

        logger.info(
            "[VectorStore] 初始化 | dir=%s | collection=%s | metric=%s",
            config.persist_directory,
            config.collection_name,
            config.distance_metric,
        )

    # ── 属性 ──────────────────────────────────────────────────────────

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    # ── 公开接口 ──────────────────────────────────────────────────────

    def initialize(self) -> None:
        """加载已有数据，若不存在则创建空库"""
        persist_dir = Path(self.config.persist_directory)
        persist_dir.mkdir(parents=True, exist_ok=True)

        data_file = self._data_file_path()

        if data_file.exists():
            try:
                self._load_from_file(data_file)
                logger.info(
                    "[VectorStore] ✅ 加载集合 '%s' | 文档数=%d | 维度=%d",
                    self.config.collection_name,
                    self.count(),
                    self._vectors.shape[1] if self._vectors is not None else 0,
                )
            except Exception:
                logger.exception("[VectorStore] ⚠ 加载失败，从空库开始")
                self._clear()
        else:
            logger.info("[VectorStore] 数据文件不存在，创建空库: %s", data_file)
            self._clear()

        self._initialized = True

    def add_embeddings(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """批量添加向量和文档（添加后立即持久化）"""
        self._ensure_initialized()

        if not ids:
            return

        # 转 numpy 并 L2 归一化（归一化后 dot product = cosine similarity）
        new_vecs = np.array(embeddings, dtype=np.float32)
        norms = np.linalg.norm(new_vecs, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-10)  # 防止除零
        new_vecs = new_vecs / norms

        if metadatas is None:
            metadatas = [{}] * len(ids)

        assert len(ids) == len(documents) == len(metadatas) == new_vecs.shape[0], (
            f"参数长度不一致: ids={len(ids)}, docs={len(documents)}, "
            f"meta={len(metadatas)}, vecs={new_vecs.shape[0]}"
        )

        self._ids.extend(ids)
        self._documents.extend(documents)
        self._metadatas.extend(metadatas)

        if self._vectors is None:
            self._vectors = new_vecs
        else:
            self._vectors = np.vstack([self._vectors, new_vecs])

        # 立即持久化
        self._save_to_file()

        logger.debug("[VectorStore] 添加 %d 条 | 总计 %d", len(ids), len(self._ids))

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, Any]] = None,
    ) -> List[SearchHit]:
        """余弦相似度 Top-K 检索"""
        self._ensure_initialized()

        if self._vectors is None or len(self._ids) == 0:
            logger.debug("[VectorStore] search: 空库，返回空结果")
            return []

        # 归一化查询向量
        query: np.ndarray = np.array(query_embedding, dtype=np.float32)
        query = query / (np.linalg.norm(query) + 1e-10)

        # 余弦相似度（存储向量已归一化 → dot = cosine）
        scores: np.ndarray = np.dot(self._vectors, query)  # shape (N,)

        # Top-K
        k = min(top_k, len(scores))
        if k == 0:
            return []

        top_indices = np.argsort(scores)[-k:][::-1]  # 降序

        hits: List[SearchHit] = []
        for idx in top_indices:
            i = int(idx)
            hits.append(
                SearchHit(
                    chunk_id=self._ids[i],
                    content=self._documents[i],
                    metadata=(
                        self._metadatas[i] if i < len(self._metadatas) else {}
                    ),
                    score=float(scores[i]),
                )
            )

        logger.debug("[VectorStore] search: top_k=%d → 返回 %d 条", top_k, len(hits))
        return hits

    def get_collection_stats(self) -> Dict[str, Any]:
        """获取集合统计信息"""
        if not self._initialized:
            return {"status": "not_initialized", "count": 0}

        dim = self._vectors.shape[1] if self._vectors is not None else 0
        file_size = 0
        data_file = self._data_file_path()
        if data_file.exists():
            file_size = data_file.stat().st_size

        return {
            "status": "ready",
            "name": self.config.collection_name,
            "count": len(self._ids),
            "dimension": dim,
            "file_size_bytes": file_size,
            "persist_directory": self.config.persist_directory,
            "backend": "numpy+json",
        }

    def delete_collection(self) -> None:
        """删除集合（清空内存 + 删除文件）"""
        self._clear()

        data_file = self._data_file_path()
        if data_file.exists():
            data_file.unlink()
            logger.warning("[VectorStore] 集合 '%s' 已删除", self.config.collection_name)
        else:
            logger.info("[VectorStore] 集合文件不存在，跳过删除")

    def count(self) -> int:
        """返回已存储文档数"""
        return len(self._ids)

    # ── 内部方法 ──────────────────────────────────────────────────────

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("VectorStore 未初始化，请先调用 initialize()")

    def _clear(self) -> None:
        self._ids = []
        self._documents = []
        self._metadatas = []
        self._vectors = None

    def _data_file_path(self) -> Path:
        return Path(self.config.persist_directory) / f"{self.config.collection_name}.json"

    def _save_to_file(self) -> None:
        """原子写入：先写 .tmp 再 rename，防止损坏"""
        data_file = self._data_file_path()
        data_file.parent.mkdir(parents=True, exist_ok=True)

        entries: List[Dict[str, Any]] = []
        if self._vectors is not None:
            for i in range(len(self._ids)):
                entries.append(
                    {
                        "id": self._ids[i],
                        "document": self._documents[i],
                        "metadata": (
                            self._metadatas[i]
                            if i < len(self._metadatas)
                            else {}
                        ),
                        "embedding": self._vectors[i].tolist(),
                    }
                )

        payload: Dict[str, Any] = {
            "format_version": self._FORMAT_VERSION,
            "collection_name": self.config.collection_name,
            "dimension": int(self._vectors.shape[1]) if self._vectors is not None else 0,
            "distance_metric": self.config.distance_metric,
            "entries": entries,
        }

        tmp_file = data_file.with_suffix(".json.tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)

        # 跨平台原子替换
        os.replace(tmp_file, data_file)

    def _load_from_file(self, data_file: Path) -> None:
        """从 JSON 文件加载数据"""
        with open(data_file, "r", encoding="utf-8") as f:
            data: Dict[str, Any] = json.load(f)

        version = data.get("format_version", 0)
        if version != self._FORMAT_VERSION:
            logger.warning(
                "[VectorStore] 格式版本不匹配: 文件=%d, 期待=%d，尝试兼容读取",
                version,
                self._FORMAT_VERSION,
            )

        entries: List[Dict[str, Any]] = data.get("entries", [])

        self._ids = []
        self._documents = []
        self._metadatas = []
        vecs_list: List[List[float]] = []

        for entry in entries:
            self._ids.append(entry["id"])
            self._documents.append(entry["document"])
            self._metadatas.append(entry.get("metadata", {}))
            vecs_list.append(entry.get("embedding", []))

        if vecs_list and all(len(v) > 0 for v in vecs_list):
            self._vectors = np.array(vecs_list, dtype=np.float32)
        else:
            self._vectors = None
