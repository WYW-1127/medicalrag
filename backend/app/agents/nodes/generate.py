import re
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from app.agents.prompts import DISCLAIMER, GENERATE_SYSTEM
from app.agents.state import AgentState, NodeUpdate, StepEvent
from app.agents.streaming import token_sink
from app.core.providers.llm import ChatMessage, LLMProvider

_CITATION_RE = re.compile(r"\[(\d+)\]")


def build_context(chunks: list[Any]) -> str:
    """编号资料块（含来源元数据），供生成与校验共用。"""
    blocks = []
    for i, c in enumerate(chunks, 1):
        blocks.append(f"[{i}]（来源：{c.source}｜章节：{c.section_path or '无'}）\n{c.text}")
    return "\n\n".join(blocks)


def parse_citations(
    answer: str, chunks: list[Any]
) -> tuple[str, list[dict[str, Any]]]:
    """提取回答中的 [n] 引用角标并映射到 chunk 元数据（按首次出现去重）。

    source 存文件名（入库的 source 是路径，展示层只要名字）。
    """
    seen: dict[int, dict[str, Any]] = {}
    for match in _CITATION_RE.finditer(answer):
        no = int(match.group(1))
        if 1 <= no <= len(chunks) and no not in seen:
            c = chunks[no - 1]
            seen[no] = {
                "no": no,
                "chunk_id": c.chunk_id,
                "text": c.text[:200],
                "source": Path(c.source).name,
                "section_path": c.section_path,
                "page": c.page,
            }
    return answer, list(seen.values())


def make_generate_node(
    llm: LLMProvider,
) -> Callable[[AgentState], Awaitable[NodeUpdate]]:
    """生成节点：仅依据编号资料回答并标注引用；verify 失败时吸收 issues 再生成。"""

    async def generate_node(state: AgentState) -> NodeUpdate:
        t0 = time.perf_counter()
        messages = [
            ChatMessage(role="system", content=GENERATE_SYSTEM),
            ChatMessage(
                role="user",
                content=f"问题：{state.query}\n\n编号资料：\n{build_context(state.chunks)}",
            ),
        ]
        regen_note = ""
        if state.verify is not None and not state.verify.passed and state.verify.issues:
            regen_note = (
                "；已根据审核意见修正（此前版本的问题："
                + "；".join(state.verify.issues[:3]) + "）"
            )
            messages.append(
                ChatMessage(
                    role="user",
                    content=(
                        "你上一版回答存在以下未被资料支持的问题，请严格修正：\n- "
                        + "\n- ".join(state.verify.issues[:5])
                    ),
                )
            )
        # token_sink 存在时流式生成并逐 token 回调（SSE），否则整段返回
        sink = token_sink.get()
        if sink is not None:
            parts: list[str] = []
            async for tok in llm.chat_stream(messages, temperature=0.3):
                parts.append(tok)
                sink(tok)
            answer = "".join(parts)
        else:
            answer = await llm.chat(messages, temperature=0.3)
        answer, citations = parse_citations(answer, state.chunks)
        # 每次生成都是全新回答，统一追加一次免责声明（再生成会整体替换 answer）
        final_answer = answer + DISCLAIMER
        ev = StepEvent(
            name="generate",
            ms=(time.perf_counter() - t0) * 1000,
            detail=f"{len(citations)} 个引用{regen_note[:30]}",
        )
        return {
            "answer": final_answer,
            "citations": citations,
            "regen_count": state.regen_count + 1,
            "steps": [*state.steps, ev],
        }

    return generate_node
