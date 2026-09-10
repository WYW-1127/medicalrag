"""检索质量指标（纯函数，二值相关性）。"""

import math


def recall_at_k(ranked_ids: list[str], gt: set[str], k: int) -> float:
    """top-k 中命中的 ground-truth 比例。"""
    if not gt:
        return 0.0
    hits = sum(1 for cid in ranked_ids[:k] if cid in gt)
    return hits / len(gt)


def mrr(ranked_ids: list[str], gt: set[str]) -> float:
    """首个命中 chunk 的倒数排名（无命中记 0）。"""
    for rank, cid in enumerate(ranked_ids, start=1):
        if cid in gt:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(ranked_ids: list[str], gt: set[str], k: int) -> float:
    """二值相关性的归一化折损累计增益：DCG/IDCG。"""
    if not gt:
        return 0.0

    def dcg(ids: list[str]) -> float:
        return sum(
            (1.0 if cid in gt else 0.0) / math.log2(rank + 1)
            for rank, cid in enumerate(ids[:k], start=1)
        )

    ideal = list(gt)[:k]
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, len(ideal) + 1))
    if idcg == 0:
        return 0.0
    return dcg(ranked_ids) / idcg
