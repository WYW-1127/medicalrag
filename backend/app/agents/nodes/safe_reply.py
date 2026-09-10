import time

from app.agents.prompts import CHITCHAT_REPLY, RISK_REPLY_TEMPLATE
from app.agents.state import AgentState, NodeUpdate, StepEvent


async def safe_reply_node(state: AgentState) -> NodeUpdate:
    """安全回复节点：急症→就医指引模板；闲聊→固定引导语。不进检索链。"""
    t0 = time.perf_counter()
    analysis = state.analysis
    if analysis is not None and analysis.intent == "risk":
        answer = RISK_REPLY_TEMPLATE.format(
            risk_type=analysis.risk_type or "疑似急症表现"
        )
        detail = f"风险拦截: {analysis.risk_type or 'risk'}"
    else:
        answer = CHITCHAT_REPLY
        detail = "闲聊引导"
    ev = StepEvent(name="safe_reply", ms=(time.perf_counter() - t0) * 1000, detail=detail)
    return {"answer": answer, "route": "safe", "steps": [*state.steps, ev]}
