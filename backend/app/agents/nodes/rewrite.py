import time
from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from app.agents.llm_io import ask_json
from app.agents.prompts import REWRITE_SYSTEM
from app.agents.state import AgentState, NodeUpdate, StepEvent
from app.core.providers.llm import LLMProvider


class RewriteOutput(BaseModel):
    rewritten: str


def _history_block(state: AgentState, limit: int = 6) -> str:
    """最近几轮对话，供指代消解。"""
    if not state.history:
        return "（无历史，本轮是首问）"
    lines = [f"{m.role}: {m.content}" for m in state.history[-limit:]]
    return "\n".join(lines)


def make_rewrite_node(llm: LLMProvider) -> Callable[[AgentState], Awaitable[NodeUpdate]]:
    """查询改写节点：指代消解 + 术语化 + 吸收 grade 反馈。"""

    async def rewrite_node(state: AgentState) -> NodeUpdate:
        t0 = time.perf_counter()
        user_parts = [f"用户查询：{state.query}", f"对话历史：\n{_history_block(state)}"]
        if state.feedback:
            user_parts.append(
                f"注意：上一次检索效果不佳，原因：{state.feedback}。请显著调整改写角度。"
            )
        out = await ask_json(llm, REWRITE_SYSTEM, "\n\n".join(user_parts), RewriteOutput)
        ev = StepEvent(
            name="rewrite",
            ms=(time.perf_counter() - t0) * 1000,
            detail=f"iteration={state.iteration + 1} -> {out.rewritten[:40]}",
        )
        return {
            "rewritten": out.rewritten,
            "iteration": state.iteration + 1,
            "steps": [*state.steps, ev],
        }

    return rewrite_node
