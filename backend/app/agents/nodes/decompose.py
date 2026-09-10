import time
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, Field

from app.agents.llm_io import ask_json
from app.agents.prompts import DECOMPOSE_SYSTEM
from app.agents.state import AgentState, NodeUpdate, StepEvent
from app.core.config import AgentSettings
from app.core.providers.llm import LLMProvider


class DecomposeOutput(BaseModel):
    sub_queries: list[str] = Field(default_factory=list)


def make_decompose_node(
    llm: LLMProvider, settings: AgentSettings
) -> Callable[[AgentState], Awaitable[NodeUpdate]]:
    """查询分解节点：对比/多跳问题拆子查询，简单问题透传。"""

    async def decompose_node(state: AgentState) -> NodeUpdate:
        t0 = time.perf_counter()
        # prompt 含 JSON 花括号，不能用 str.format——用占位符替换
        system = DECOMPOSE_SYSTEM.replace(
            "{subquery_max}", str(settings.subquery_max)
        )
        query = state.rewritten or state.query
        out = await ask_json(
            llm, system, f"需要分解的查询：{query}", DecomposeOutput
        )
        subs = [q.strip() for q in out.sub_queries if q.strip()]
        subs = subs[: settings.subquery_max] or [query]  # 空输出兜底为原查询
        ev = StepEvent(
            name="decompose",
            ms=(time.perf_counter() - t0) * 1000,
            detail=f"{len(subs)} 路子查询",
        )
        return {"sub_queries": subs, "steps": [*state.steps, ev]}

    return decompose_node
