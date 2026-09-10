from app.rag.models import RetrievedChunk


def _own_score(chunk: RetrievedChunk) -> float:
    """该 chunk 在其来源列表中的自身分数（dense 路存 dense_score，sparse 路存 sparse_score）。"""
    if chunk.dense_score is not None:
        return chunk.dense_score
    if chunk.sparse_score is not None:
        return chunk.sparse_score
    return 0.0


def _merge(target: RetrievedChunk, other: RetrievedChunk) -> None:
    """把 other 携带的分数字段合并进 target（不覆盖已有值）。"""
    if other.dense_score is not None and target.dense_score is None:
        target.dense_score = other.dense_score
    if other.sparse_score is not None and target.sparse_score is None:
        target.sparse_score = other.sparse_score


def rrf_fuse(
    result_lists: list[list[RetrievedChunk]], k: int = 60
) -> list[RetrievedChunk]:
    """Reciprocal Rank Fusion：score = Σ 1/(k + rank + 1)，跨列表去重合并。

    返回新对象列表（model_copy），按 fused_score 降序；不修改输入。
    """
    chunks: dict[str, RetrievedChunk] = {}
    scores: dict[str, float] = {}
    for results in result_lists:
        for rank, chunk in enumerate(results):
            cid = chunk.chunk_id
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
            if cid in chunks:
                _merge(chunks[cid], chunk)
            else:
                chunks[cid] = chunk.model_copy()
    fused: list[RetrievedChunk] = []
    for cid, score in scores.items():
        c = chunks[cid]
        c.fused_score = score
        fused.append(c)
    fused.sort(key=lambda c: c.fused_score or 0.0, reverse=True)
    return fused


def weighted_fuse(
    result_lists: list[list[RetrievedChunk]], weights: list[float]
) -> list[RetrievedChunk]:
    """加权融合：每列表内 min-max 归一化（span=0 记 1.0），score = Σ w_i × norm_i。"""
    chunks: dict[str, RetrievedChunk] = {}
    scores: dict[str, float] = {}
    for results, weight in zip(result_lists, weights, strict=True):
        if not results:
            continue
        lo = min(_own_score(c) for c in results)
        hi = max(_own_score(c) for c in results)
        for c in results:
            norm = (_own_score(c) - lo) / (hi - lo) if hi > lo else 1.0  # span=0：全部记满分
            scores[c.chunk_id] = scores.get(c.chunk_id, 0.0) + weight * norm
            if c.chunk_id in chunks:
                _merge(chunks[c.chunk_id], c)
            else:
                chunks[c.chunk_id] = c.model_copy()
    fused: list[RetrievedChunk] = []
    for cid, score in scores.items():
        c = chunks[cid]
        c.fused_score = score
        fused.append(c)
    fused.sort(key=lambda c: c.fused_score or 0.0, reverse=True)
    return fused
