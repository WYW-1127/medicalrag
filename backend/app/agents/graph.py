"""LangGraph 图组装：MedicalRAG Agentic 问答状态机。

START → analyze ─┬─(risk|chitchat)→ safe_reply → END
                 └─(medical)→ rewrite → decompose → retrieve → grade
                     ↑                                      ├─ generate → verify ─┬─ END
                     └── retry（低置信重写）←───────────────┤                      └─ regen→generate
                                                            └─ fallback → END
"""

from typing import Any

from app.agents.nodes.analyze import make_analyze_node, route_after_analyze
from app.agents.nodes.decompose import make_decompose_node
from app.agents.nodes.fallback import fallback_node
from app.agents.nodes.generate import make_generate_node
from app.agents.nodes.grade import make_grade_node, route_after_grade
from app.agents.nodes.retrieve import make_retrieve_node
from app.agents.nodes.rewrite import make_rewrite_node
from app.agents.nodes.safe_reply import safe_reply_node
from app.agents.nodes.verify import make_verify_node, route_after_verify
from app.agents.state import AgentResult, AgentState
from app.core.config import Settings, get_settings
from app.core.providers.llm import ChatMessage, LLMProvider
from app.rag.retriever import HybridRetriever


class MedicalRAGAgent:
    """Agentic 问答入口：P4 CLI 直接用；P5 API 在此之上接 SSE 与会话。"""

    def __init__(
        self,
        *,
        llm: LLMProvider | None = None,
        retriever: HybridRetriever | None = None,
        settings: Settings | None = None,
    ) -> None:
        from langgraph.graph import END, START, StateGraph

        self._settings = settings or get_settings()
        self._llm = llm or LLMProvider(self._settings.llm)
        retriever = retriever or HybridRetriever(settings=self._settings)
        agent_cfg = self._settings.agent

        builder: Any = StateGraph(AgentState)

        # langgraph 的 _Node 协议重载极严（与 Callable[[AgentState], Awaitable[dict]]
        # 不兼容），注册处统一按 Any 传递——运行时签名完全正确
        nodes: dict[str, Any] = {
            "analyze": make_analyze_node(self._llm),
            "safe_reply": safe_reply_node,
            "rewrite": make_rewrite_node(self._llm),
            "decompose": make_decompose_node(self._llm, agent_cfg),
            "retrieve": make_retrieve_node(retriever, self._settings.retrieval.rerank_k),
            "grade": make_grade_node(self._llm, agent_cfg),
            "generate": make_generate_node(self._llm),
            "verify": make_verify_node(self._llm),
            "fallback": fallback_node,
        }
        for name, fn in nodes.items():
            builder.add_node(name, fn)

        builder.add_edge(START, "analyze")
        builder.add_conditional_edges(
            "analyze", route_after_analyze, {"safe": "safe_reply", "medical": "rewrite"}
        )
        builder.add_edge("safe_reply", END)
        builder.add_edge("rewrite", "decompose")
        builder.add_edge("decompose", "retrieve")
        builder.add_edge("retrieve", "grade")
        builder.add_conditional_edges(
            "grade",
            lambda s: route_after_grade(s, agent_cfg),
            {"generate": "generate", "retry": "rewrite", "fallback": "fallback"},
        )
        builder.add_edge("generate", "verify")
        builder.add_conditional_edges(
            "verify",
            lambda s: route_after_verify(s, agent_cfg.max_regenerate),
            {"end": END, "regenerate": "generate", "fallback": "fallback"},
        )
        builder.add_edge("fallback", END)
        self._graph = builder.compile()

    async def run(
        self, query: str, history: list[ChatMessage] | None = None
    ) -> AgentResult:
        raw = await self._graph.ainvoke(
            AgentState(query=query, history=history or [])
        )
        # langgraph 版本差异：ainvoke 可能返回 dict 或 state 实例
        final = raw if isinstance(raw, AgentState) else AgentState.model_validate(raw)
        return AgentResult(
            route=final.route or "answered",
            answer=final.answer,
            citations=final.citations,
            steps=final.steps,
        )
