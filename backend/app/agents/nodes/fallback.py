import time

from app.agents.prompts import FALLBACK_REPLY
from app.agents.state import AgentState, NodeUpdate, StepEvent


async def fallback_node(state: AgentState) -> NodeUpdate:
    """拒答兜底：证据不足或校验失败耗尽重试时，明确拒答并给建议。"""
    t0 = time.perf_counter()
    reason = "证据不足" if state.verify is None or state.verify.passed else "回答未能通过引用校验"
    ev = StepEvent(name="fallback", ms=(time.perf_counter() - t0) * 1000, detail=reason)
    return {"answer": FALLBACK_REPLY, "route": "fallback", "steps": [*state.steps, ev]}
