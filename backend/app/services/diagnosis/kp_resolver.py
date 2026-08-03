"""知识点名称对齐器 — kp_name (LLM 输出) → kp_id (UUID, 系统唯一键空间)

背景 (P0 修复):
    LLM 在对话中只能产出人类可读的知识点名称，而 AOO 引擎全程使用 kp_id (UUID)
    作为索引键 (见 fitness_calculator.KnowledgeGraph.kp_index)。
    若不做对齐，中文名会与 UUID 键空间错配，导致:
      1. 掌握度融合分支恒不命中 → LLM 评估被静默丢弃
      2. 中文名混入 focus_areas → AOO 无法识别，污染优化目标

设计原则:
    - **只输出 kp_id，绝不输出名称**。对齐不上的信号一律丢弃并记日志，不硬塞。
    - 匹配阶梯: 精确 → 归一化 → 别名/标签 → 包含 → 模糊(difflib)，阈值可配置。
    - 带进程内缓存 + TTL，避免每轮问答都全表扫描。
"""

from __future__ import annotations

import logging
import re
import time
import unicodedata
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.knowledge_point import KnowledgePoint

logger = logging.getLogger(__name__)

# 映射缓存 TTL (秒)，知识图谱是低频变更数据
_CACHE_TTL = 300

# 归一化时剔除的标点/空白
_PUNCT_RE = re.compile(r"[\s\-_·・.。，,、:：;；()（）\[\]【】/\\]+")


def normalize_name(raw: str) -> str:
    """名称归一化: 全角→半角、去标点空白、转小写

    使 "二叉 树（BST）" 与 "二叉树BST" 能够匹配。
    """
    if not raw:
        return ""
    # NFKC 统一全角/半角、兼容字符
    s = unicodedata.normalize("NFKC", str(raw))
    s = _PUNCT_RE.sub("", s)
    return s.strip().lower()


class KnowledgePointResolver:
    """知识点名称 → kp_id 对齐器 (进程内缓存)"""

    # 类级缓存: 所有实例共享，避免 Celery worker 内重复加载
    _exact: Dict[str, str] = {}       # 归一化名称 → kp_id
    _alias: Dict[str, str] = {}       # 归一化别名/标签 → kp_id
    _id_to_name: Dict[str, str] = {}  # kp_id → 原始名称 (仅用于日志)
    _loaded_at: float = 0.0

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------
    # 缓存加载
    # ------------------------------------------------------------

    @classmethod
    def invalidate_cache(cls) -> None:
        """知识图谱变更后主动失效缓存"""
        cls._loaded_at = 0.0

    async def _ensure_loaded(self, force: bool = False) -> None:
        cls = type(self)
        if not force and cls._exact and (time.time() - cls._loaded_at) < _CACHE_TTL:
            return

        exact: Dict[str, str] = {}
        alias: Dict[str, str] = {}
        id_to_name: Dict[str, str] = {}

        try:
            result = await self.db.execute(
                select(KnowledgePoint.id, KnowledgePoint.name, KnowledgePoint.tags)
            )
            for kp_id, name, tags in result.all():
                sid = str(kp_id)
                id_to_name[sid] = name
                key = normalize_name(name)
                if key:
                    # 同名冲突时保留首个，避免后者覆盖导致不确定性
                    exact.setdefault(key, sid)
                for tag in (tags or []):
                    if not isinstance(tag, str):
                        continue
                    tkey = normalize_name(tag)
                    # 别名不覆盖正名
                    if tkey and tkey not in exact:
                        alias.setdefault(tkey, sid)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[kp-resolver] 加载知识点映射失败: %s", exc)
            return

        cls._exact = exact
        cls._alias = alias
        cls._id_to_name = id_to_name
        cls._loaded_at = time.time()
        logger.debug(
            "[kp-resolver] 映射已加载: %d 个知识点, %d 个别名",
            len(exact), len(alias),
        )

    # ------------------------------------------------------------
    # 对齐
    # ------------------------------------------------------------

    async def resolve(self, raw_name: str) -> Optional[str]:
        """将单个名称对齐到 kp_id，失败返回 None (不猜测、不伪造)"""
        if not raw_name or not str(raw_name).strip():
            return None

        await self._ensure_loaded()
        cls = type(self)
        if not cls._exact:
            return None

        raw = str(raw_name).strip()

        # 0) 本身就是合法 kp_id (LLM 白名单模式下的理想情况)
        if raw in cls._id_to_name:
            return raw

        key = normalize_name(raw)
        if not key:
            return None

        # 1) 精确 (归一化后)
        if key in cls._exact:
            return cls._exact[key]

        # 2) 别名 / 标签
        if key in cls._alias:
            return cls._alias[key]

        # 3) 唯一包含关系 — 仅在候选唯一时才采纳，避免歧义
        contains = [
            kid for k, kid in cls._exact.items()
            if len(k) >= 2 and (k in key or key in k)
        ]
        if len(set(contains)) == 1:
            return contains[0]

        # 4) 模糊匹配 (difflib)，需超过阈值
        threshold = float(settings.CHAT_KP_FUZZY_THRESHOLD)
        best_id: Optional[str] = None
        best_score = 0.0
        for k, kid in cls._exact.items():
            score = SequenceMatcher(None, key, k).ratio()
            if score > best_score:
                best_score = score
                best_id = kid
        if best_id and best_score >= threshold:
            logger.debug(
                "[kp-resolver] 模糊命中 '%s' → '%s' (score=%.3f)",
                raw, cls._id_to_name.get(best_id, best_id), best_score,
            )
            return best_id

        logger.info(
            "[kp-resolver] 无法对齐知识点 '%s' (best=%.3f < %.2f)，已丢弃",
            raw, best_score, threshold,
        )
        return None

    async def resolve_many(
        self, raw_names: List[str]
    ) -> Tuple[Dict[str, str], List[str]]:
        """批量对齐

        Returns:
            (resolved, unresolved)
            resolved: {原始名称: kp_id}
            unresolved: 未能对齐的原始名称列表
        """
        resolved: Dict[str, str] = {}
        unresolved: List[str] = []
        for name in raw_names:
            kid = await self.resolve(name)
            if kid:
                resolved[name] = kid
            else:
                unresolved.append(name)
        return resolved, unresolved

    async def name_of(self, kp_id: str) -> Optional[str]:
        """kp_id → 名称 (用于向用户解释路径变更原因)"""
        await self._ensure_loaded()
        return type(self)._id_to_name.get(str(kp_id))
