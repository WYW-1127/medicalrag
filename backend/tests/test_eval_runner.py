"""评估 runner 单测：FakeRetriever/FakeAgent/ScriptedLLM 注入。"""

from app.agents.state import AgentResult, StepEvent
from app.core.config import Settings
from app.evaluation.dataset import EvalQuestion
from app.evaluation.runner import run_agent_eval, run_retrieval_eval
from app.rag.models import RetrievalResult, RetrievedChunk
from tests.test_node_analyze import ScriptedLLM


class RankRetriever:
    """按查询前缀返回脚本化排名（模拟检索质量）。"""

    def __init__(self, ranking_by_prefix: dict[str, list[str]]) -> None:
        self.ranking_by_prefix = ranking_by_prefix
        self.calls: list[str] = []

    async def retrieve(self, query: str, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(query)
        ids = next(
            (ids for prefix, ids in self.ranking_by_prefix.items()
             if query.startswith(prefix)),
            [],
        )
        chunks = [
            RetrievedChunk(chunk_id=cid, text=f"{cid} 的内容", rerank_score=0.9 - i * 0.1)
            for i, cid in enumerate(ids)
        ]
        return RetrievalResult(query=query, final=chunks)


def _qs(*specs: tuple[str, list[str]]) -> list[EvalQuestion]:
    return [
        EvalQuestion(id=f"q{i}", question=prefix + "的问题", ground_truth=gt)
        for i, (prefix, gt) in enumerate(specs)
    ]


async def test_retrieval_eval_three_configs():
    settings = Settings(_env_file=None)
    made: list[str] = []

    def factory(s: Settings) -> RankRetriever:
        made.append(s.retrieval.fusion)
        return RankRetriever({  # gt 命中于第 1/3 位
            "甲": ["gt1", "x", "gt2"], "乙": ["x", "y", "gt3"],
        })

    qs = _qs(("甲", ["gt1", "gt2"]), ("乙", ["gt3"]))
    results = await run_retrieval_eval(qs, settings, retriever_factory=factory, k=3)
    assert set(results) == {"dense_only", "hybrid_rrf", "hybrid_rerank"}
    assert len(made) == 3  # 每配置构造了一个 retriever
    for _name, m in results.items():
        assert m["n"] == 2
        assert 0.0 <= m["recall@3"] <= 1.0


async def test_retrieval_metrics_values():
    settings = Settings(_env_file=None)
    factory = lambda s: RankRetriever({"甲": ["gt1", "x"]})  # noqa: E731
    results = await run_retrieval_eval(
        _qs(("甲", ["gt1"])), settings, retriever_factory=factory, k=2
    )
    for m in results.values():  # gt 在 rank1 → 全指标应为 1.0
        assert m["recall@2"] == 1.0 and m["mrr"] == 1.0 and m["ndcg@2"] == 1.0


class FakeAgent:
    """按查询类别返回路由：in→answered，oog→fallback，risk→safe。"""

    async def run(self, query: str, history=None):  # type: ignore[no-untyped-def]
        if query.startswith("急症") or query.startswith("不想活"):
            route = "safe"
        elif query.startswith("库外"):
            route = "fallback"
        else:
            route = "answered"
        return AgentResult(
            route=route,
            answer="标准答案[1]。" if route == "answered" else "无法回答",
            citations=[{"no": 1}] if route == "answered" else [],
            steps=[StepEvent(name="analyze", ms=1)],
            final_chunks=[
                RetrievedChunk(chunk_id="gt1", text="支撑资料", rerank_score=0.9)
            ],
        )


async def test_agent_eval_routes_and_judges():
    llm = ScriptedLLM(
        ['{"score": 0.9, "issues": []}', '{"score": 1.0, "issues": []}']  # faith, relev
    )
    in_kb = [EvalQuestion(id="i1", question="库内问题")]
    oog = [EvalQuestion(id="o1", question="库外问题", category="out_of_kb")]
    risk = [EvalQuestion(id="r1", question="急症胸痛", category="risk")]
    res = await run_agent_eval(in_kb, oog, risk, FakeAgent(), llm)  # type: ignore[arg-type]
    assert res.in_kb_answered_rate == 1.0
    assert res.refusal_rate == 1.0
    assert res.risk_intercept_rate == 1.0
    assert res.faithfulness_avg == 0.9 and res.relevancy_avg == 1.0
    assert res.samples[0]["citations"] == 1


async def test_agent_eval_unanswered_skips_judge():
    class FallbackOnlyAgent(FakeAgent):
        async def run(self, query: str, history=None):  # type: ignore[no-untyped-def]
            r = await super().run(query, history)
            return r.model_copy(update={"route": "fallback"}) if False else AgentResult(
                route="fallback", answer="拒答", citations=[], steps=[],
                final_chunks=[],
            )

    llm = ScriptedLLM([])  # 不应被调用
    res = await run_agent_eval(
        [EvalQuestion(id="i1", question="库内问题")], [], [], FallbackOnlyAgent(), llm  # type: ignore[arg-type]
    )
    assert res.in_kb_answered_rate == 0.0
    assert not llm.calls
