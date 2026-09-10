from typing import Any

import pytest

from app.core.config import RetrievalSettings, Settings
from app.core.providers.embedding import EmbeddingProvider
from app.core.providers.reranker import RerankerProvider
from app.rag.retriever import HybridRetriever


def _hit(cid: str, distance: float, text: str = "正文", department: str = "心血管"):
    return {"id": cid, "distance": distance,
            "entity": {"text": text, "section_path": "指南 > 章节", "department": department,
                       "doc_type": "guideline", "source": "x.pdf", "page": 1, "seq": 0}}


class FakeClient:
    def __init__(self) -> None:
        self.searches: list[dict[str, Any]] = []

    def load_collection(self, name: str) -> None:
        pass

    def search(self, collection_name, data, anns_field, limit, filter,
               output_fields, search_params=None):  # type: ignore[no-untyped-def]
        self.searches.append({
            "anns_field": anns_field, "limit": limit, "filter": filter,
            "data_len": len(data[0]) if isinstance(data[0], list) else len(data),
        })
        # dense 路：A > B；sparse 路：B > C（B 两路都出现，RRF 应显著提权 B）
        if anns_field == "dense":
            return [[_hit("A", 0.9), _hit("B", 0.8), _hit("C", 0.7)]]
        return [[_hit("B", 5.0), _hit("C", 4.0)]]


class FakeEmbedder(EmbeddingProvider):
    def __init__(self) -> None:
        pass  # 不调用父类构造（无需真实 settings）

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 8 for _ in texts]


class FakeReranker(RerankerProvider):
    def __init__(self, order: list[int]) -> None:
        self.order = order
        self.received_texts: list[str] | None = None

    async def rerank(self, query: str, documents: list[str]):
        from app.core.providers.reranker import RerankResult
        self.received_texts = documents
        return [RerankResult(index=i, score=0.9 - n * 0.1) for n, i in enumerate(self.order)]


def _make_retriever(reranker=None):
    settings = Settings(_env_file=None)
    return HybridRetriever(
        client=FakeClient(), embedder=FakeEmbedder(),  # type: ignore[arg-type]
        reranker=reranker or FakeReranker(order=[1, 0, 2]), settings=settings,
    )


async def test_two_way_recall_and_fusion():
    r = _make_retriever()
    result = await r.retrieve("高血压诊断", use_rerank=False)
    fields = [s["anns_field"] for s in r._client.searches]  # noqa: SLF001
    assert fields == ["dense", "sparse"]  # 两路都发起
    assert result.recalled_dense == 3 and result.recalled_sparse == 2
    # B 在 dense rank1 + sparse rank0：1/62 + 1/61，应高于 A（仅 dense rank0 = 1/61）
    assert result.final[0].chunk_id == "B"


async def test_rerank_reorders_and_truncates():
    # 融合顺序 B(0.0325)>C(0.0320)>A(0.0164)；FakeReranker 指定 [2,1,0] → A,C,B，top_k=2 → A,C
    r = _make_retriever(reranker=FakeReranker(order=[2, 1, 0]))
    result = await r.retrieve("q", top_k=2)
    assert [c.chunk_id for c in result.final] == ["A", "C"]
    assert result.final[0].rerank_score == pytest.approx(0.9)
    assert all(c.rerank_score is not None for c in result.final)


async def test_rerank_text_truncated():
    r = _make_retriever(reranker=FakeReranker(order=[0]))
    await r.retrieve("q", top_k=1)
    texts = r._reranker.received_texts  # noqa: SLF001
    assert texts is not None and all(len(t) <= 1000 for t in texts)  # type: ignore[arg-type]


async def test_filter_passed_to_both_routes():
    r = _make_retriever()
    await r.retrieve("q", department="内分泌", doc_type="guideline")
    for s in r._client.searches:  # noqa: SLF001
        assert s["filter"] == 'department == "内分泌" and doc_type == "guideline"'


async def test_no_rerank_returns_fused_topk():
    r = _make_retriever()
    result = await r.retrieve("q", top_k=1, use_rerank=False)
    assert [c.chunk_id for c in result.final] == ["B"]
    assert result.final[0].rerank_score is None


async def test_timings_recorded():
    r = _make_retriever()
    result = await r.retrieve("q")
    names = [t.name for t in result.timings]
    assert names == ["embed_query", "recall", "fuse", "rerank"]
    assert all(t.ms >= 0 for t in result.timings)


async def test_unknown_fusion_raises():
    r = _make_retriever()
    with pytest.raises(ValueError):
        await r.retrieve("q", fusion="nope")


def test_settings_defaults():
    rs = RetrievalSettings()
    assert rs.recall_k == 50 and rs.rerank_k == 30 and rs.top_k == 8
    assert rs.fusion == "rrf"
