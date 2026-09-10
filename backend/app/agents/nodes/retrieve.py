import asyncio
import time
from collections.abc import Awaitable, Callable

from app.agents.state import AgentState, NodeUpdate, StepEvent
from app.rag.models import RetrievedChunk
from app.rag.retriever import HybridRetriever


def _best(a: RetrievedChunk, b: RetrievedChunk) -> RetrievedChunk:
    """同 chunk_id 保留排序分更高者（rerank 优先，其次 fused）。"""

    def key(c: RetrievedChunk) -> float:
        return c.rerank_score if c.rerank_score is not None else (c.fused_score or 0.0)

    return a if key(a) >= key(b) else b


def make_retrieve_node(
    retriever: HybridRetriever, rerank_k: int = 30
) -> Callable[[AgentState], Awaitable[NodeUpdate]]:
    """检索节点：子查询并行检索，按 chunk_id 去重合并后取前 rerank_k。"""

    async def retrieve_node(state: AgentState) -> NodeUpdate:
        t0 = time.perf_counter()
        queries = state.sub_queries or [state.rewritten or state.query]
        results = await asyncio.gather(
            *[retriever.retrieve(q) for q in queries]
        )
        merged: dict[str, RetrievedChunk] = {}
        for r in results:
            for c in r.final:
                merged[c.chunk_id] = _best(merged[c.chunk_id], c) if c.chunk_id in merged else c
        chunks = sorted(
            merged.values(),
            key=lambda c: (
                c.rerank_score if c.rerank_score is not None else (c.fused_score or 0.0)
            ),
            reverse=True,
        )[:rerank_k]
        ev = StepEvent(
            name="retrieve",
            ms=(time.perf_counter() - t0) * 1000,
            detail=f"{len(queries)} 路子查询 → {len(chunks)} chunks",
        )
        return {"chunks": chunks, "steps": [*state.steps, ev]}

    return retrieve_node
