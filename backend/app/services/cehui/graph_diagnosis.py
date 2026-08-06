"""知识图谱驱动测绘 — 沿图谱采样题目 + 沿边传播掌握度

设计目标（建议 1）:
  将测绘从「按题目聚合掌握度」升级为「沿图谱节点采样题目 → 沿边传播掌握度
  （前置薄弱则下游降权）」。

核心能力:
  1. sample_questions_by_graph: 按图层（基础层/核心层/进阶层）分层按比例抽题；
     若提供 seed_kp_ids（薄弱根节点），优先抽取其所在子树。
  2. propagate_mastery: 沿 prerequisite 边向上传播，若前置节点掌握度不足，
     则下游节点掌握度乘以惩罚系数（可配置）。

向后兼容:
  - 无知识图谱（节点/边为空）或题库为 Mock 字符串 kp_id 时，调用方应回退到
    原有的 random.sample 逻辑，本模块不做强制依赖。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# 层级 → 默认抽题比例（基础层 50% / 核心层 30% / 进阶层 20%）
DEFAULT_LAYER_RATIO: Dict[str, float] = {
    "基础层": 0.50,
    "核心层": 0.30,
    "进阶层": 0.20,
}
# 兜底层级名（图谱未标注 layer 时按难度 1-2/3/4-5 归层）
_TIER_BY_DIFFICULTY = {1: "基础层", 2: "基础层", 3: "核心层", 4: "进阶层", 5: "进阶层"}
# 难度缺失（题库 difficulty 为 null）时，按题目 id 稳定散列均匀摊到三层的序列
_LAYERS_CYCLE = ["基础层", "基础层", "核心层", "进阶层"]


def _layer_of_difficulty(difficulty, _seed: str = "") -> str:
    """已知难度按 _TIER_BY_DIFFICULTY 归层；null 难度按题目 id 稳定散列均匀分布。

    与 paper_assembler._tier_of 同理：约 47.5% 题目缺难度标注，若一律归入核心层会
    破坏 50/30/20 分层均衡，这里用 id 哈希让它们按比例摊开到基础/核心/进阶层。
    """
    try:
        d = int(difficulty)
    except (TypeError, ValueError):
        d = None
    if d in _TIER_BY_DIFFICULTY:
        return _TIER_BY_DIFFICULTY[d]
    h = 0
    for ch in str(_seed):
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return _LAYERS_CYCLE[h % len(_LAYERS_CYCLE)]

# 掌握度传播惩罚系数：前置掌握度 < PENALTY_THRESHOLD 时下游乘以该系数
PENALTY_COEFFICIENT = 0.85
PENALTY_THRESHOLD = 0.60


@dataclass
class GraphNode:
    """知识图谱节点（轻量表示，避免直接依赖 ORM 对象）"""

    kp_id: str
    name: str = ""
    layer: Optional[str] = None
    difficulty: int = 1
    # 前置知识点 id 列表（前置 → 本节点 的依赖方向）
    prerequisites: List[str] = field(default_factory=list)

    def effective_layer(self) -> str:
        """若未标注 layer，则按难度归层"""
        if self.layer and self.layer in DEFAULT_LAYER_RATIO:
            return self.layer
        return _TIER_BY_DIFFICULTY.get(self.difficulty, "核心层")


@dataclass
class CehuiGraph:
    """知识图谱（节点 + 边），由调用方从 ORM 或外部注入"""

    nodes: Dict[str, GraphNode] = field(default_factory=dict)
    # prerequisite 边: target_kp_id -> [source_kp_id, ...]
    prereq_edges: Dict[str, List[str]] = field(default_factory=dict)

    @classmethod
    def from_orm(
        cls,
        knowledge_points: List,
        edges: List,
        name_map: Optional[Dict[str, str]] = None,
    ) -> "CehuiGraph":
        """从 ORM 对象构建图谱。

        Args:
            knowledge_points: KnowledgePoint ORM 实例列表，需含 id/name/layer/
                difficulty_level 属性。
            edges: KnowledgeGraphEdge ORM 实例列表，需含 source_kp_id/
                target_kp_id/relation_type 属性。
            name_map: 备用名称映射（kp_id str -> name），用于补全节点名。
        """
        name_map = name_map or {}
        nodes: Dict[str, GraphNode] = {}
        for kp in knowledge_points:
            kid = str(kp.id)
            nodes[kid] = GraphNode(
                kp_id=kid,
                name=getattr(kp, "name", "") or name_map.get(kid, kid),
                layer=getattr(kp, "layer", None),
                difficulty=getattr(kp, "difficulty_level", 1) or 1,
            )
        prereq_edges: Dict[str, List[str]] = {}
        for e in edges:
            rel = getattr(e, "relation_type", "prerequisite")
            if rel != "prerequisite":
                continue
            src = str(e.source_kp_id)
            tgt = str(e.target_kp_id)
            prereq_edges.setdefault(tgt, []).append(src)
        # 回填每个节点的 prerequisites 列表
        for tgt, sources in prereq_edges.items():
            if tgt in nodes:
                nodes[tgt].prerequisites = sources
        return cls(nodes=nodes, prereq_edges=prereq_edges)

    def is_empty(self) -> bool:
        return len(self.nodes) == 0

    def descendants(self, root_ids: List[str]) -> List[str]:
        """返回 root_ids 所在子树的全部节点（含自身），用于薄弱根节点优先采样"""
        visited: set = set()
        stack = list(root_ids)
        while stack:
            cur = stack.pop()
            if cur in visited or cur not in self.nodes:
                continue
            visited.add(cur)
            # 后置节点：prereq_edges 中 target=cur 的 source 是它的前置；
            # 其子节点是所有以 cur 为前置的节点（即 prereq_edges 中 source 含 cur 的 target）
            for tgt, sources in self.prereq_edges.items():
                if cur in sources and tgt not in visited:
                    stack.append(tgt)
        return list(visited)


def sample_questions_by_graph(
    graph: CehuiGraph,
    bank: List[dict],
    total: int = 20,
    seed_kp_ids: Optional[List[str]] = None,
    layer_ratio: Optional[Dict[str, float]] = None,
) -> Tuple[List[dict], Dict[str, Dict[str, int]]]:
    """沿知识图谱分层均衡抽题。

    Args:
        graph: 知识图谱（含节点 layer / difficulty）。
        bank: 题库（题目 dict 列表），每题需含 kp_id 与 difficulty。
        total: 总抽题数。
        seed_kp_ids: 薄弱根节点 id 列表，若提供则优先抽取其所在子树题目。
        layer_ratio: 层级抽题比例，默认 DEFAULT_LAYER_RATIO。

    Returns:
        (questions, allocation)
        - questions: 抽中的题目列表（按 layer 顺序分层排列）。
        - allocation: {kp_id: {tier: n}} 每知识点各层抽题数（供前端展示均衡度）。
    """
    if graph.is_empty():
        # 无图谱：调用方应回退 random.sample，这里返回空交由上层降级
        return [], {}

    ratio = layer_ratio or DEFAULT_LAYER_RATIO

    # 将题目按 (kp_id, 题目所属 layer) 分桶；题目 layer 取自其知识点节点
    def _question_layer(q: dict) -> str:
        kid = str(q.get("kp_id", ""))
        node = graph.nodes.get(kid)
        if node is not None:
            # 节点已标 layer 直接用；否则按难度（含 null 散列）归层
            if node.layer and node.layer in DEFAULT_LAYER_RATIO:
                return node.layer
            return _layer_of_difficulty(q.get("difficulty"), _seed=q.get("id", ""))
        # 题目自带难度时按难度归层（兜底）
        return _layer_of_difficulty(q.get("difficulty", 3), _seed=q.get("id", ""))

    # 建立 layer -> [题目] 桶
    layer_buckets: Dict[str, List[dict]] = {lyr: [] for lyr in ratio}
    for q in bank:
        lyr = _question_layer(q)
        layer_buckets.setdefault(lyr, []).append(q)

    # 若指定了 seed 薄弱根，优先将其子树知识点对应的题目前置
    seed_set = set()
    if seed_kp_ids:
        seed_set = set(graph.descendants(seed_kp_ids))

    # 计算各层配额（至少 1 题，避免 0；剩余给基础层）
    raw_counts = {lyr: total * r for lyr, r in ratio.items()}
    layer_counts = {lyr: max(1, int(round(c))) for lyr, c in raw_counts.items()}
    # 校正总数
    diff_total = total - sum(layer_counts.values())
    if diff_total != 0:
        # 把差值补到占比最大的层
        top_layer = max(ratio, key=ratio.get)
        layer_counts[top_layer] = max(1, layer_counts[top_layer] + diff_total)

    sampled: List[dict] = []
    allocation: Dict[str, Dict[str, int]] = {}

    # 关键约束：每知识点至少 1 题（保证「覆盖所有知识点」）。
    # 早期实现仅按层配额 bucket[:need] 顺序取题，当某层题目集中在某些知识点时，
    # 尾部知识点会被漏掉（实测 11 个知识点只覆盖 9 个）。这里先为每层每个知识点
    # 各取 1 题打底，再用剩余配额按层比例补足「层次感」，差额跨层转移。
    # 优先 seed 薄弱子树的知识点取这 1 题底。
    def _bucket_for_layer(lyr: str) -> List[dict]:
        return layer_buckets.get(lyr, [])

    # 1) 打底：每层每个知识点各 1 题（优先 seed 子树）
    base_picked: List[dict] = []
    for lyr in ratio:
        bucket = _bucket_for_layer(lyr)
        if not bucket:
            continue
        # 按知识点分组，每组优先取 seed 子树题
        by_kp: Dict[str, List[dict]] = {}
        for q in bucket:
            by_kp.setdefault(str(q.get("kp_id", "")), []).append(q)
        for kid, items in by_kp.items():
            if kid in seed_set:
                pick = next((q for q in items if str(q.get("kp_id", "")) in seed_set), items[0])
            else:
                pick = items[0]
            base_picked.append(pick)
            allocation.setdefault(kid, {})
            allocation[kid][lyr] = allocation[kid].get(lyr, 0) + 1

    base_count = len(base_picked)
    sampled.extend(base_picked)

    # 2) 补足层次感：剩余配额按层比例分配，层内优先 seed 子树再补其余
    remaining = max(0, total - base_count)
    if remaining > 0:
        # 各层剩余配额（按层比例，至少 0，封顶到该层可用题数）
        layer_remain = {
            lyr: max(0, layer_counts[lyr] - sum(1 for q in base_picked if _question_layer(q) == lyr))
            for lyr in ratio
        }
        # 用 remaining 回填（先按 ratio 比例，再校正总数）
        raw_rem = {lyr: remaining * ratio[lyr] for lyr in ratio}
        rem_counts = {lyr: max(0, int(round(c))) for lyr, c in raw_rem.items()}
        diff = remaining - sum(rem_counts.values())
        if diff != 0:
            top = max(ratio, key=ratio.get)
            rem_counts[top] = max(0, rem_counts[top] + diff)

        for lyr in ratio:
            bucket = _bucket_for_layer(lyr)
            if not bucket:
                continue
            need = rem_counts[lyr]
            if need <= 0:
                continue
            # 已选题集合，避免重复
            picked_ids = {id(q) for q in sampled}
            seed_pool = [q for q in bucket if str(q.get("kp_id", "")) in seed_set and id(q) not in picked_ids]
            rest_pool = [q for q in bucket if str(q.get("kp_id", "")) not in seed_set and id(q) not in picked_ids]
            chosen = seed_pool[:need] + rest_pool[: max(0, need - len(seed_pool))]
            for q in chosen:
                sampled.append(q)
                kid = str(q.get("kp_id", ""))
                allocation.setdefault(kid, {})
                allocation[kid][lyr] = allocation[kid].get(lyr, 0) + 1

    return sampled, allocation


def propagate_mastery(
    raw_mastery: Dict[str, float],
    graph: CehuiGraph,
    penalty_coefficient: float = PENALTY_COEFFICIENT,
    penalty_threshold: float = PENALTY_THRESHOLD,
) -> Dict[str, float]:
    """沿 prerequisite 边传播掌握度：前置薄弱则下游降权。

    仅对图谱中存在、且 raw_mastery 中已评估的节点生效；Mock 字符串 kp_id
    不在图谱中时自动跳过（保持原值）。

    Args:
        raw_mastery: {kp_id: mastery} 由 IRT 直接估计的原始掌握度。
        graph: 知识图谱。
        penalty_coefficient: 惩罚系数（前置不足时下游乘以它）。
        penalty_threshold: 前置掌握度低于此值视为薄弱。

    Returns:
        修正后的 {kp_id: mastery}，范围裁剪到 [0, 1]。
    """
    corrected = {k: float(v) for k, v in raw_mastery.items()}

    for tgt, sources in graph.prereq_edges.items():
        if tgt not in corrected:
            continue
        # 若任一前置节点掌握度低于阈值，则对下游节点施加惩罚
        weak_prereq = any(
            corrected.get(src, 1.0) < penalty_threshold for src in sources
        )
        if weak_prereq:
            corrected[tgt] = round(
                max(0.0, min(1.0, corrected[tgt] * penalty_coefficient)), 3
            )

    return corrected
