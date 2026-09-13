from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.providers.llm import ChatMessage, LLMProvider
from app.main import app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class ScriptedLLM(LLMProvider):
    """按脚本顺序返回预设回复的假 LLM（各 Agent 节点测试共用）。"""

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls: list[list[ChatMessage]] = []

    async def chat(self, messages, *, temperature=None):  # type: ignore[no-untyped-def]
        self.calls.append(list(messages))
        if not self.replies:
            raise AssertionError("脚本回复耗尽")
        return self.replies.pop(0)
