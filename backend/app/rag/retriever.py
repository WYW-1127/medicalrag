import asyncio
import time
from typing import Any, cast

from loguru import logger

from app.core.config import Settings, get_settings
from app.core.providers.embedding import EmbeddingProvider
from app.core.providers.reranker import RerankerProvider
from app.rag.fusion import rrf_fuse, weighted_fuse
from app.rag.models import RetrievalResult, RetrievedChunk, StageTiming

_OUTPUT_FIELDS = [
    "text",
    "section_path",
    "department",
    "doc_type",
    "source",
    "page",
    "seq",
]


class HybridRetriever:
    """两阶段检索：dense + BM25 双路并行召回 → 手写融合 → cross-encoder 重排。

    每阶段耗时记入 RetrievalResult.timings（P5 SSE step 事件的数据源）。
    全部依赖可注入（client/embedder/reranker），单测不碰真实服务。
    """

    def __init__(
        self,
        *,
        client: Any | None = None,
        embedder: EmbeddingProvider | None = None,
        reranker: RerankerProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        from pymilvus import MilvusClient

        self._settings = settings or get_settings()
        self._client = client or MilvusClient(uri=self._settings.milvus_uri)
        self._embedder = embedder or EmbeddingProvider(self._settings.embedding)
        self._reranker = reranker or RerankerProvider(self._settings.reranker)
        self._collection = self._settings.milvus_collection
        self._client.load_collection(self._collection)

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        recall_k: int | None = None,
        fusion: str | None = None,
        department: str | None = None,
        doc_type: str | None = None,
        use_rerank: bool = True,
    ) -> RetrievalResult:
        rs = self._settings.retrieval
        top_k = top_k or rs.top_k
        recall_k = recall_k or rs.recall_k
        fusion = fusion or rs.fusion
        timings: list[StageTiming] = []

        t0 = time.perf_counter()
        vec = (await self._embedder.embed([query]))[0]
        timings.append(StageTiming(name="embed_query", ms=_ms_since(t0)))

        filt = self._build_filter(department, doc_type)
        t0 = time.perf_counter()
        # pymilvus 是同步 SDK，放线程池并行跑两路召回
        dense_hits, sparse_hits = await asyncio.gather(
            asyncio.to_thread(self._dense_search, vec, recall_k, filt),
            asyncio.to_thread(self._sparse_search, query, recall_k, filt),
        )
        timings.append(StageTiming(name="recall", ms=_ms_since(t0)))
        dense = [self._to_chunk(h, "dense") for h in dense_hits]
        sparse = [self._to_chunk(h, "sparse") for h in sparse_hits]
        logger.info("召回 dense={} sparse={} filter={!r}", len(dense), len(sparse), filt)

        t0 = time.perf_counter()
        if fusion == "rrf":
            fused = rrf_fuse([dense, sparse], k=rs.rrf_k)
        elif fusion == "weighted":
            fused = weighted_fuse(
                [dense, sparse], [rs.dense_weight, rs.sparse_weight]
            )
        else:
            raise ValueError(f"未知融合策略: {fusion}")
        fused = fused[: rs.rerank_k]
        timings.append(StageTiming(name="fuse", ms=_ms_since(t0)))

        if use_rerank and fused:
            t0 = time.perf_counter()
            final = await self._rerank_chunks(query, fused, top_k)
            timings.append(StageTiming(name="rerank", ms=_ms_since(t0)))
        else:
            final = fused[:top_k]

        return RetrievalResult(
            query=query,
            fused=fused,
            final=final,
            timings=timings,
            recalled_dense=len(dense),
            recalled_sparse=len(sparse),
        )

    # ---- 召回 ----
    def _dense_search(
        self, vec: list[float], k: int, filt: str
    ) -> list[dict[str, Any]]:
        res = self._client.search(
            self._collection,
            data=[vec],
            anns_field="dense",
            limit=k,
            filter=filt,
            output_fields=_OUTPUT_FIELDS,
            search_params={"metric_type": "COSINE"},
        )
        return cast("list[dict[str, Any]]", res[0])

    def _sparse_search(self, query: str, k: int, filt: str) -> list[dict[str, Any]]:
        res = self._client.search(
            self._collection,
            data=[query],  # BM25 函数字段直接传查询文本
            anns_field="sparse",
            limit=k,
            filter=filt,
            output_fields=_OUTPUT_FIELDS,
        )
        return cast("list[dict[str, Any]]", res[0])

    @staticmethod
    def _to_chunk(hit: dict[str, Any], route: str) -> RetrievedChunk:
        ent = hit["entity"]
        return RetrievedChunk(
            chunk_id=hit["chunk_id"],  # MilvusClient 以主键字段名返回 id
            text=ent.get("text", ""),
            dense_score=hit["distance"] if route == "dense" else None,
            sparse_score=hit["distance"] if route == "sparse" else None,
            section_path=ent.get("section_path", ""),
            department=ent.get("department", ""),
            doc_type=ent.get("doc_type", ""),
            source=ent.get("source", ""),
            page=ent.get("page", 0),
            seq=ent.get("seq", 0),
        )

    @staticmethod
    def _build_filter(department: str | None, doc_type: str | None) -> str:
        parts: list[str] = []
        if department:
            parts.append(f'department == "{department.replace(chr(34), chr(92) + chr(34))}"')
        if doc_type:
            parts.append(f'doc_type == "{doc_type.replace(chr(34), chr(92) + chr(34))}"')
        return " and ".join(parts)

    # ---- 精排 ----
    async def _rerank_chunks(
        self, query: str, chunks: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        """重排仅用于打分：文本截断到 1000 字符（对齐 rerank 模型 token 上限）。"""
        results = await self._reranker.rerank(query, [c.text[:1000] for c in chunks])
        final: list[RetrievedChunk] = []
        for r in results[:top_k]:
            c = chunks[r.index]
            c.rerank_score = r.score
            final.append(c)
        return final


def _ms_since(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000
