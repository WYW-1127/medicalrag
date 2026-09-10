import time
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, Field

from app.agents.llm_io import ask_json
from app.agents.prompts import GRADE_SYSTEM
from app.agents.state import AgentState, NodeUpdate, StepEvent
from app.core.config import AgentSettings
from app.core.providers.llm import LLMProvider


class GradeOutput(BaseModel):
    scores: list[float] = Field(default_factory=list)


def make_grade_node(
    llm: LLMProvider, settings: AgentSettings
) -> Callable[[AgentState], Awaitable[NodeUpdate]]:
    """检索反思节点（Self-RAG 式）：对 chunk 逐条相关性打分。"""

    async def grade_node(state: AgentState) -> NodeUpdate:
        t0 = time.perf_counter()
        query = state.rewritten or state.query
        lines = [f"[{i+1}] {c.text[:400]}" for i, c in enumerate(state.chunks)]
        out = await ask_json(
            llm, GRADE_SYSTEM, f"查询：{query}\n\n资料：\n" + "\n".join(lines), GradeOutput
        )
        scores = [max(0.0, min(1.0, s)) for s in out.scores][: len(state.chunks)]
        scores += [0.0] * (len(state.chunks) - len(scores))  # 缺项补 0
        relevant = sum(1 for s in scores if s >= settings.grade_threshold)
        top = max(scores, default=0.0)
        # 不达标时预写反馈（路由函数是纯函数，不能改状态；达标时清空旧反馈）
        feedback = (
            ""
            if relevant >= settings.grade_min_relevant
            else (
                f"检索结果相关性不足（最高分 {top:.2f} < 阈值 {settings.grade_threshold}）。"
                "请尝试：使用更规范的医学术语、更换同义表述、或把问题拆得更具体。"
            )
        )
        ev = StepEvent(
            name="grade",
            ms=(time.perf_counter() - t0) * 1000,
            detail=f"相关 {relevant}/{len(scores)}，最高分 {top:.2f}",
        )
        return {"grades": scores, "feedback": feedback, "steps": [*state.steps, ev]}

    return grade_node


def route_after_grade(state: AgentState, settings: AgentSettings) -> str:
    """三向路由：达标生成 / 未达标重写（feedback 已由 grade 节点写入）/ 迭代耗尽拒答。"""
    relevant = sum(1 for s in state.grades if s >= settings.grade_threshold)
    if relevant >= settings.grade_min_relevant:
        return "generate"
    if state.iteration < settings.max_rewrite_iterations:
        return "retry"
    return "fallback"
