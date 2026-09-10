import time
from collections.abc import Awaitable, Callable

from app.agents.llm_io import ask_json
from app.agents.prompts import ANALYZE_SYSTEM
from app.agents.state import AgentState, NodeUpdate, QueryAnalysis, StepEvent
from app.core.providers.llm import LLMProvider


def make_analyze_node(llm: LLMProvider) -> Callable[[AgentState], Awaitable[NodeUpdate]]:
    """查询分析节点：意图分类 + 风险检测（医学安全前置闸门）。"""

    async def analyze_node(state: AgentState) -> NodeUpdate:
        t0 = time.perf_counter()
        analysis = await ask_json(llm, ANALYZE_SYSTEM, state.query, QueryAnalysis)
        ev = StepEvent(
            name="analyze",
            ms=(time.perf_counter() - t0) * 1000,
            detail=f"intent={analysis.intent} {analysis.reason[:40]}",
        )
        return {"analysis": analysis, "steps": [*state.steps, ev]}

    return analyze_node


def route_after_analyze(state: AgentState) -> str:
    """条件路由：risk/chitchat → 安全回复；medical → 检索链。"""
    if state.analysis is None:
        return "safe"
    if state.analysis.intent in ("risk", "chitchat"):
        return "safe"
    return "medical"
