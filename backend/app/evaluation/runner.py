"""消融评估编排：检索层三配置 + Agentic 层（生成/安全指标）。"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.agents.graph import MedicalRAGAgent
from app.core.config import Settings
from app.core.providers.llm import LLMProvider
from app.evaluation.dataset import EvalQuestion
from app.evaluation.judge import judge_faithfulness, judge_relevancy
from app.evaluation.metrics import mrr, ndcg_at_k, recall_at_k
from app.rag.retriever import HybridRetriever

RETRIEVAL_CONFIGS: dict[str, dict[str, Any]] = {
    "dense_only": {"fusion": "weighted", "dense_weight": 1.0, "sparse_weight": 0.0,
                   "use_rerank": False},
    "hybrid_rrf": {"fusion": "rrf", "use_rerank": False},
    "hybrid_rerank": {"fusion": "rrf", "use_rerank": True},
}


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


async def run_retrieval_eval(
    questions: list[EvalQuestion],
    base_settings: Settings,
    retriever_factory: Callable[[Settings], HybridRetriever] | None = None,
    k: int = 5,
) -> dict[str, dict[str, float]]:
    """三配置消融：每题检索一次，计算 Recall@k / MRR / nDCG@k。"""
    results: dict[str, dict[str, float]] = {}
    factory = retriever_factory or (lambda s: HybridRetriever(settings=s))
    for name, cfg in RETRIEVAL_CONFIGS.items():
        settings = base_settings.model_copy(deep=True)
        settings.retrieval.fusion = cfg["fusion"]
        settings.retrieval.dense_weight = cfg.get("dense_weight", 0.5)
        settings.retrieval.sparse_weight = cfg.get("sparse_weight", 0.5)
        retriever = factory(settings)
        recalls: list[float] = []
        mrrs: list[float] = []
        ndcgs: list[float] = []
        for q in questions:
            r = await retriever.retrieve(q.question, top_k=k,
                                         use_rerank=cfg["use_rerank"])
            ids = [c.chunk_id for c in r.final]
            gt = set(q.ground_truth)
            recalls.append(recall_at_k(ids, gt, k))
            mrrs.append(mrr(ids, gt))
            ndcgs.append(ndcg_at_k(ids, gt, k))
        results[name] = {
            f"recall@{k}": _mean(recalls),
            "mrr": _mean(mrrs),
            f"ndcg@{k}": _mean(ndcgs),
            "n": float(len(questions)),
        }
    return results


@dataclass
class AgentEvalResult:
    refusal_rate: float = 0.0  # 知识库外拒答率（目标高）
    risk_intercept_rate: float = 0.0  # 急症拦截率（目标高）
    in_kb_answered_rate: float = 0.0  # 知识库内正常回答率（目标高）
    faithfulness_avg: float = 0.0
    relevancy_avg: float = 0.0
    samples: list[dict[str, Any]] = field(default_factory=list)


async def run_agent_eval(
    in_kb: list[EvalQuestion],
    oog: list[EvalQuestion],
    risk: list[EvalQuestion],
    agent: MedicalRAGAgent,
    judge_llm: LLMProvider,
) -> AgentEvalResult:
    """Agentic 全链路评估：judge 评 in-KB 回答；OOG/风险评路由正确性。"""
    result = AgentEvalResult()

    faiths: list[float] = []
    relevs: list[float] = []
    answered = 0
    for q in in_kb:
        r = await agent.run(q.question)
        if r.route == "answered":
            answered += 1
            contexts = [c.text for c in r.final_chunks]
            f = await judge_faithfulness(judge_llm, q.question, r.answer, contexts)
            rv = await judge_relevancy(judge_llm, q.question, r.answer)
            faiths.append(f.score)
            relevs.append(rv.score)
            result.samples.append({
                "id": q.id, "question": q.question, "route": r.route,
                "faithfulness": f.score, "relevancy": rv.score,
                "citations": len(r.citations),
                "faith_issues": f.issues[:2],
            })
        else:
            result.samples.append({
                "id": q.id, "question": q.question, "route": r.route,
                "faithfulness": None, "relevancy": None, "citations": 0,
                "faith_issues": [],
            })
    result.in_kb_answered_rate = answered / len(in_kb) if in_kb else 0.0
    result.faithfulness_avg = _mean(faiths)
    result.relevancy_avg = _mean(relevs)

    refusals = 0
    for q in oog:
        if (await agent.run(q.question)).route == "fallback":
            refusals += 1
    result.refusal_rate = refusals / len(oog) if oog else 0.0

    intercepted = 0
    for q in risk:
        if (await agent.run(q.question)).route == "safe":
            intercepted += 1
    result.risk_intercept_rate = intercepted / len(risk) if risk else 0.0
    return result
