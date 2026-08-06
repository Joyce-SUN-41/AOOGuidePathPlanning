"""分层分级均衡组卷（建议 2）

取代原有的 random.sample 粗放抽题：
  - 维度一（知识点）：覆盖 N 个核心知识点，按权重（或均分）分配每桶题数。
  - 维度二（难度阶）：difficulty 1-5 映射为 一阶(1-2)/二阶(3)/三阶(4-5)，
    每桶内按 50/30/20 配额等比抽取，保证至少覆盖两个难度阶。
  - 组合约束：单知识点桶上限 4 题（防一次塞太多跟不上）；不足跨桶补足。
  - 输出：组卷明细 allocation = {kp_id: {tier1:n, tier2:n, tier3:n}} 供前端展示均衡度。

与建议 1（图谱驱动）的关系：
  - /questions 优先使用图谱驱动采样（图层更准、可 seed 薄弱子树）；
  - 无图谱 / Mock 模式 / 图谱抽题失败时，回退到本均衡组卷（而非纯随机）。
  - 两者都返回 allocation，前端统一展示“本次组卷均衡度”。
"""

from typing import Dict, List, Optional, Tuple

# 难度阶定义：一阶=基础(1-2) / 二阶=应用(3) / 三阶=综合(4-5)
TIER_BY_DIFFICULTY = {1: "tier1", 2: "tier1", 3: "tier2", 4: "tier3", 5: "tier3"}
# 各难度阶默认配额比例（合计 1.0）
DEFAULT_TIER_RATIO: Dict[str, float] = {"tier1": 0.50, "tier2": 0.30, "tier3": 0.20}
# 单知识点桶题目上限
MAX_PER_KP = 4
# 每桶至少覆盖的难度阶数
MIN_TIERS_PER_KP = 2
# 难度缺失时（题库 difficulty 为 null）均匀轮换的难度阶序列，保证三阶按比例摊开
_TIERS_CYCLE = ["tier1", "tier1", "tier2", "tier3"]


def _tier_of(difficulty, _seed: str = "") -> str:
    """将难度映射为难度阶。

    已知难度按 1-2→tier1 / 3→tier2 / 4-5→tier3 归层。
    题库中约 47.5% 的题目 difficulty 为 null —— 若一律归入某一固定阶会破坏
    50/30/20 的分层均衡。这里用题目 id 的哈希做确定性散列，把 null 题稳定地
    均匀摊到三个阶（按 50/30/20 的比例轮换），使分层配额真实生效。
    """
    try:
        d = int(difficulty)
    except (TypeError, ValueError):
        d = None
    if d in TIER_BY_DIFFICULTY:
        return TIER_BY_DIFFICULTY[d]
    # 难度缺失：基于题目 id 的稳定散列，按 _TIERS_CYCLE 比例分布
    h = 0
    for ch in str(_seed):
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return _TIERS_CYCLE[h % len(_TIERS_CYCLE)]


def assemble_balanced_paper(
    bank: List[dict],
    total: int = 20,
    kp_weights: Optional[Dict[str, float]] = None,
) -> Tuple[List[dict], Dict[str, Dict[str, int]]]:
    """分层分级均衡组卷。

    Args:
        bank: 题库（题目 dict 列表），每题需含 kp_id 与 difficulty。
        total: 总抽题数。
        kp_weights: 知识点权重 {kp_id: w}，提供则按权重分配每桶题数，否则均分。

    Returns:
        (questions, allocation)
        - questions: 抽中的题目列表（按知识点分组、桶内按难度阶排序）。
        - allocation: {kp_id: {tier1:n, tier2:n, tier3:n}} 组卷均衡明细。
    """
    if not bank:
        return [], {}

    # 1. 按 kp_id 分桶（兼容 kp_ids 数组：取首个作为主知识点）
    kp_buckets: Dict[str, List[dict]] = {}
    for q in bank:
        kid = str(q.get("kp_id", "") or "")
        if not kid and q.get("kp_ids"):
            first = q["kp_ids"][0] if isinstance(q["kp_ids"], (list, tuple)) else q["kp_ids"]
            kid = str(first)
        if not kid:
            continue
        kp_buckets.setdefault(kid, []).append(q)

    if not kp_buckets:
        # 无 kp_id 信息：退回整体随机
        import random

        sampled = random.sample(bank, min(total, len(bank)))
        return sampled, {}

    kp_ids = list(kp_buckets.keys())

    # 2. 计算每桶题数（按权重或均分），取整且至少 1，单桶上限 MAX_PER_KP
    if kp_weights:
        total_w = sum(kp_weights.get(k, 1.0) for k in kp_ids) or len(kp_ids)
        kp_quota = {
            k: max(1, round(total * (kp_weights.get(k, 1.0) / total_w)))
            for k in kp_ids
        }
    else:
        base = total // len(kp_ids)
        kp_quota = {k: max(1, base) for k in kp_ids}

    # 校正：把超出总额的差值从超额桶回收，补到不足桶
    def _reconcile(quota: Dict[str, int], cap: int) -> Dict[str, int]:
        q = dict(quota)
        # 先封顶
        for k in q:
            q[k] = min(q[k], cap, len(kp_buckets[k]))
        # 超出总额则按桶大小递减回收
        over = sum(q.values()) - total
        while over > 0:
            # 从题数最多且 >1 的桶减 1
            cand = [k for k in q if q[k] > 1]
            if not cand:
                break
            victim = max(cand, key=lambda k: q[k])
            q[victim] -= 1
            over -= 1
        # 不足总额则补到还能加的桶
        under = total - sum(q.values())
        while under > 0:
            cand = [k for k in q if q[k] < min(cap, len(kp_buckets[k]))]
            if not cand:
                break
            benef = max(cand, key=lambda k: len(kp_buckets[k]) - q[k])
            q[benef] += 1
            under -= 1
        return q

    kp_quota = _reconcile(kp_quota, MAX_PER_KP)

    # 3. 每桶内按难度阶均衡抽取
    sampled: List[dict] = []
    allocation: Dict[str, Dict[str, int]] = {}

    for kid in kp_ids:
        bucket = kp_buckets[kid]
        need = kp_quota[kid]
        # 每桶内按 tier 再分桶
        tier_buckets: Dict[str, List[dict]] = {t: [] for t in DEFAULT_TIER_RATIO}
        for q in bucket:
            tier_buckets[_tier_of(q.get("difficulty"), _seed=q.get("id", ""))].append(q)

        # 本桶各 tier 配额（至少覆盖 MIN_TIERS_PER_KP 个 tier）
        raw = {t: need * r for t, r in DEFAULT_TIER_RATIO.items()}
        tier_counts = {t: max(0, int(round(c))) for t, c in raw.items()}
        # 保证至少覆盖 MIN_TIERS_PER_KP 个有题的 tier
        available_tiers = [t for t in DEFAULT_TIER_RATIO if tier_buckets[t]]
        if available_tiers:
            for t in available_tiers[:MIN_TIERS_PER_KP]:
                tier_counts[t] = max(tier_counts[t], 1)
        # 校正桶内总数 = need
        diff_bucket = need - sum(tier_counts.values())
        if diff_bucket != 0:
            top_tier = max(
                (t for t in DEFAULT_TIER_RATIO if tier_buckets[t]),
                key=lambda t: DEFAULT_TIER_RATIO[t],
                default="tier1",
            )
            tier_counts[top_tier] = max(0, tier_counts[top_tier] + diff_bucket)

        chosen_for_kp: List[dict] = []
        for t in DEFAULT_TIER_RATIO:
            pool = tier_buckets[t]
            if not pool:
                continue
            pick = pool[: tier_counts[t]]
            chosen_for_kp.extend(pick)

        # 若因题目不足未达 need，用同桶剩余题补足
        if len(chosen_for_kp) < need:
            remainder = [q for q in bucket if q not in chosen_for_kp]
            chosen_for_kp.extend(remainder[: need - len(chosen_for_kp)])

        sampled.extend(chosen_for_kp)
        # 记录 allocation
        alloc_kp: Dict[str, int] = {}
        for q in chosen_for_kp:
            t = _tier_of(q.get("difficulty"), _seed=q.get("id", ""))
            alloc_kp[t] = alloc_kp.get(t, 0) + 1
        allocation[kid] = alloc_kp

    return sampled, allocation
