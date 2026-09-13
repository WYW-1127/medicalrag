import pytest

from app.agents.nodes.grade import make_grade_node, route_after_grade
from app.agents.nodes.retrieve import make_retrieve_node
from app.agents.state import AgentState
from app.core.config import AgentSettings
from app.rag.models import RetrievalResult, RetrievedChunk
from tests.conftest import ScriptedLLM


class FakeRetriever:
    """按查询返回脚本化结果的假检索器。"""

    def __init__(self, results_by_prefix: dict[str, list[str]]) -> None:
        self.results_by_prefix = results_by_prefix
        self.queries: list[str] = []

    async def retrieve(self, query: str, **kwargs):  # type: ignore[no-untyped-def]
        self.queries.append(query)
        chunks = []
        for prefix, ids in self.results_by_prefix.items():
            if query.startswith(prefix):
                chunks = [
                    RetrievedChunk(
                        chunk_id=cid, text=f"{cid} 的正文内容",
                        rerank_score=0.9 - i * 0.1,
                    )
                    for i, cid in enumerate(ids)
                ]
                break
        return RetrievalResult(query=query, final=chunks)


def _state(**kw):  # type: ignore[no-untyped-def]
    defaults = dict(query="q", rewritten="改写", sub_queries=["子查询A", "子查询B"])
    defaults.update(kw)
    return AgentState(**defaults)


async def test_retrieve_parallel_and_dedup():
    fake = FakeRetriever({"子查询A": ["c1", "c2"], "子查询B": ["c2", "c3"]})
    node = make_retrieve_node(fake, rerank_k=10)  # type: ignore[arg-type]
    update = await node(_state())
    ids = [c.chunk_id for c in update["chunks"]]
    assert sorted(ids) == ["c1", "c2", "c3"]  # c2 去重
    assert set(fake.queries) == {"子查询A", "子查询B"}
    # 去重保留高分版本：c2 来自子查询A（0.8）而非 B（0.9）？—— 保留 _best 即 rerank 高者
    c2 = next(c for c in update["chunks"] if c.chunk_id == "c2")
    assert c2.rerank_score == pytest.approx(0.9)  # 0.9 来自子查询B的 rank0


async def test_retrieve_caps_rerank_k():
    fake = FakeRetriever({"子查询A": ["c1", "c2", "c3"]})
    node = make_retrieve_node(fake, rerank_k=2)  # type: ignore[arg-type]
    update = await node(AgentState(query="q", sub_queries=["子查询A"]))
    assert len(update["chunks"]) == 2


async def test_grade_node_scores_and_feedback():
    llm = ScriptedLLM(['{"scores": [0.9, 0.1, 1.5]}'])  # 1.5 应被钳制到 1.0
    node = make_grade_node(llm, AgentSettings(grade_threshold=0.4, grade_min_relevant=2))
    state = _state(
        chunks=[RetrievedChunk(chunk_id=str(i), text="t") for i in range(3)]
    )
    update = await node(state)
    assert update["grades"] == [0.9, 0.1, 1.0]
    assert update["feedback"] == ""  # 2 个 >= 0.4，达标


async def test_grade_node_insufficient_writes_feedback():
    llm = ScriptedLLM(['{"scores": [0.1, 0.2]}'])
    node = make_grade_node(llm, AgentSettings(grade_threshold=0.4, grade_min_relevant=2))
    state = _state(chunks=[RetrievedChunk(chunk_id="a", text="t"),
                           RetrievedChunk(chunk_id="b", text="t")])
    update = await node(state)
    assert "相关性不足" in update["feedback"]


def test_route_after_grade_three_branches():
    s = AgentSettings(grade_threshold=0.4, grade_min_relevant=2, max_rewrite_iterations=2)
    ok = _state(grades=[0.9, 0.8, 0.1])
    low_but_can_retry = _state(grades=[0.1, 0.2], iteration=1)
    exhausted = _state(grades=[0.1, 0.2], iteration=2)
    assert route_after_grade(ok, s) == "generate"
    assert route_after_grade(low_but_can_retry, s) == "retry"
    assert route_after_grade(exhausted, s) == "fallback"
