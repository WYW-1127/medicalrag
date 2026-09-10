import time
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, Field

from app.agents.llm_io import ask_json
from app.agents.prompts import VERIFY_SYSTEM
from app.agents.state import AgentState, NodeUpdate, StepEvent, VerifyResult
from app.core.providers.llm import LLMProvider


class VerifyOutput(BaseModel):
    passed: bool
    issues: list[str] = Field(default_factory=list)


def make_verify_node(
    llm: LLMProvider,
) -> Callable[[AgentState], Awaitable[NodeUpdate]]:
    """忠实度校验节点：逐句核对引用是否被资料支持（防幻觉的最后闸门）。"""

    async def verify_node(state: AgentState) -> NodeUpdate:
        t0 = time.perf_counter()
        cited_blocks = []
        for c in state.citations:
            no = c["no"]
            chunk = next((x for x in state.chunks if x.chunk_id == c["chunk_id"]), None)
            if chunk is not None:
                cited_blocks.append(f"[{no}]\n{chunk.text}")
        if not cited_blocks:
            result = VerifyResult(
                passed=False, issues=["回答没有任何 [n] 引用角标，无法核验"]
            )
        else:
            raw = await ask_json(
                llm,
                VERIFY_SYSTEM,
                f"问题：{state.query}\n\n回答：\n{state.answer}\n\n被引用资料：\n"
                + "\n\n".join(cited_blocks),
                VerifyOutput,
            )
            result = VerifyResult(passed=raw.passed, issues=raw.issues)
        ev = StepEvent(
            name="verify",
            ms=(time.perf_counter() - t0) * 1000,
            detail="通过" if result.passed else f"问题: {'; '.join(result.issues[:2])}",
        )
        update: NodeUpdate = {"verify": result, "steps": [*state.steps, ev]}
        if result.passed:
            update["route"] = "answered"  # 校验通过即完成回答路径
        return update

    return verify_node


def route_after_verify(state: AgentState, max_regenerate: int) -> str:
    """校验路由：通过收尾；未过且可再生成→generate；耗尽→fallback。"""
    if state.verify is None or state.verify.passed:
        return "end"
    if state.regen_count <= max_regenerate:
        return "regenerate"
    return "fallback"
