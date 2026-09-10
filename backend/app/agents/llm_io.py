"""LLM 结构化输出工具：要求只输出 JSON + 容错解析 + 失败回传重试一次。"""

import json
import re
from typing import Any

from pydantic import BaseModel

from app.core.providers.llm import ChatMessage, LLMProvider, ProviderError

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)
_JSON_RE = re.compile(r"\{.*\}", re.S)


def extract_json(text: str) -> dict[str, Any]:
    """从 LLM 输出中提取 JSON 对象：容忍 code fence、前后废话。"""
    fenced = _FENCE_RE.search(text)
    candidate = fenced.group(1) if fenced else text
    try:
        result: dict[str, Any] = json.loads(candidate)
        return result
    except json.JSONDecodeError:
        m = _JSON_RE.search(candidate)
        if m:
            fallback: dict[str, Any] = json.loads(m.group(0))
            return fallback
        raise


async def ask_json[T: BaseModel](
    llm: LLMProvider, system: str, user: str, schema: type[T], *, temperature: float = 0.0
) -> T:
    """调用 LLM 并解析为 schema；解析失败把错误回传重试一次，再失败抛 ProviderError。"""
    messages = [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=user),
    ]
    last_error = ""
    for _ in range(2):
        if last_error:
            messages.append(
                ChatMessage(
                    role="user",
                    content=(
                        f"你上次的输出无法解析（{last_error}）。"
                        "请严格只输出符合要求的 JSON，不要包含任何其他文字。"
                    ),
                )
            )
        raw = await llm.chat(messages, temperature=temperature)
        try:
            return schema.model_validate(extract_json(raw))
        except Exception as exc:  # noqa: BLE001 统一交给重试/抛出
            last_error = str(exc)[:200]
    raise ProviderError(f"LLM 结构化输出解析失败: {last_error}")
