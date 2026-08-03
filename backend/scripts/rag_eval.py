"""RAG 检索质量离线评测脚本（零侵入，只读检索层）。

目的：用一份手工构造的「问题 → 期望命中关键词」数据集，真实调用
``KnowledgeBase.retrieve()``，量化检索层召回能力，作为论文 / 答辩的
可复现证据。**不依赖 LLM、不伪造任何数据**——所有指标均由真实向量检索产生。

指标：
- Recall@K：Top-K 命中中，至少含 1 个期望关键词的查询占比
- 命中率：相似度 >= 阈值（默认 0.5）的查询占比
- 平均检索耗时 / 平均最高相似度

运行方式：
    cd backend && python scripts/rag_eval.py
    cd backend && python scripts/rag_eval.py --top-k 5 --threshold 0.45
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── 评测数据集（手工构造，覆盖 docs/ai_course_content.md 主题）──────────
# query: 检索问题；expect: 期望在命中块中出现的任一关键词（小写匹配）
EVAL_DATASET: List[Dict[str, object]] = [
    {"query": "什么是归一化", "expect": ["归一化", "normaliz"]},
    {"query": "梯度下降的原理", "expect": ["梯度下降", "gradient"]},
    {"query": "什么是过拟合以及如何防止", "expect": ["过拟合", "overfit", "正则化"]},
    {"query": "交叉熵损失函数", "expect": ["交叉熵", "cross entropy", "loss"]},
    {"query": "反向传播算法", "expect": ["反向传播", "backprop", "链式法则"]},
    {"query": "学习率的作用", "expect": ["学习率", "learning rate"]},
    {"query": "什么是激活函数", "expect": ["激活函数", "activation", "relu"]},
    {"query": "批归一化和层归一化", "expect": ["批归一化", "batch norm", "层归一化"]},
    {"query": "注意力机制是什么", "expect": ["注意力", "attention"]},
    {"query": "什么是卷积神经网络", "expect": ["卷积", "convolution", "cnn"]},
    {"query": "dropout 正则化", "expect": ["dropout", "正则"]},
    {"query": "什么是迁移学习", "expect": ["迁移学习", "transfer"]},
    {"query": "强化学习基础", "expect": ["强化学习", "reinforcement", "奖励"]},
    {"query": "Transformer 架构", "expect": ["transformer", "自注意力", "self-attention"]},
    {"query": "什么是 embedding 向量", "expect": ["embedding", "嵌入", "向量"]},
]


def _hit_contains_keyword(retrieval_texts: List[str], keywords: List[str]) -> bool:
    """判断命中块文本中是否包含任一期望关键词"""
    joined = "\n".join(retrieval_texts).lower()
    return any(kw.lower() in joined for kw in keywords)


async def run_eval(top_k: int, threshold: float) -> Dict[str, object]:
    from app.services.rag.knowledge_base import KnowledgeBase

    kb = KnowledgeBase()
    try:
        await kb.initialize()
    except Exception as e:  # noqa: BLE001
        print(f"[rag_eval] 知识库初始化失败，退出: {e}")
        return {}

    if not kb.is_initialized or kb.vector_store.get_collection_stats().get("chunk_count", 0) == 0:
        print("[rag_eval] 向量库为空，请先索引文档（kb.index_directory）。")
        return {}

    total = len(EVAL_DATASET)
    recall_hits = 0
    threshold_hits = 0
    latencies: List[float] = []
    top_scores: List[float] = []

    print(f"\n=== RAG 检索评测 (top_k={top_k}, threshold={threshold}) ===")
    print(f"评测问题数: {total}\n")

    for i, item in enumerate(EVAL_DATASET, 1):
        query: str = item["query"]  # type: ignore[assignment]
        expect: List[str] = item["expect"]  # type: ignore[assignment]

        t0 = time.perf_counter()
        retrieval = await kb.retrieve(query, top_k=top_k, threshold=threshold)
        elapsed = (time.perf_counter() - t0) * 1000
        latencies.append(elapsed)

        texts = [h.content for h in retrieval.hits]
        has_kw = _hit_contains_keyword(texts, expect)
        if has_kw:
            recall_hits += 1
        if retrieval.hits:
            top_scores.append(retrieval.hits[0].score)
            if retrieval.hits[0].score >= threshold:
                threshold_hits += 1

        status = "OK " if has_kw else "MISS"
        top_s = f"{retrieval.hits[0].score:.3f}" if retrieval.hits else "  -  "
        print(f"[{status}] {i:2d}. {query:<22} hits={retrieval.count:<2} top={top_s} {elapsed:6.1f}ms")

    await kb.close()

    recall = recall_hits / total if total else 0.0
    thr_rate = threshold_hits / total if total else 0.0
    avg_lat = sum(latencies) / len(latencies) if latencies else 0.0
    avg_top = sum(top_scores) / len(top_scores) if top_scores else 0.0

    print("\n=== 汇总 ===")
    print(f"Recall@{top_k:<2}        : {recall:.3f} ({recall_hits}/{total})")
    print(f"阈值命中率(>={threshold}): {thr_rate:.3f} ({threshold_hits}/{total})")
    print(f"平均检索耗时        : {avg_lat:.1f} ms")
    print(f"平均最高相似度      : {avg_top:.3f}")

    return {
        "total": total,
        f"recall@{top_k}": round(recall, 3),
        "threshold_hit_rate": round(thr_rate, 3),
        "avg_latency_ms": round(avg_lat, 1),
        "avg_top_score": round(avg_top, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG 检索质量离线评测")
    parser.add_argument("--top-k", type=int, default=5, help="检索返回数量")
    parser.add_argument("--threshold", type=float, default=0.5, help="相似度阈值")
    args = parser.parse_args()

    result = asyncio.run(run_eval(args.top_k, args.threshold))
    if result:
        print("\nJSON:", result)


if __name__ == "__main__":
    main()
