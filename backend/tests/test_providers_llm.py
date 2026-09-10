from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.core.config import LLMSettings
from app.core.providers.llm import ChatMessage, LLMProvider, ProviderError


def _make_provider(client: Any) -> LLMProvider:
    return LLMProvider(LLMSettings(api_key="sk-test"), client=client)


class _FakeMessage:
    def __init__(self, content: str | None) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str | None) -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str | None) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeStream:
    """按顺序 yield delta.content（"你"、"好"、None），None 应被 chat_stream 过滤。"""

    def __init__(self) -> None:
        self._contents: list[str | None] = ["你", "好", None]

    async def __aiter__(self) -> AsyncIterator[Any]:
        for content in self._contents:

            class _Delta:
                pass

            _Delta.content = content

            class _Chunk:
                choices = [type("C", (), {"delta": _Delta()})()]

            yield _Chunk


class FakeCompletions:
    async def create(self, **kwargs: Any) -> Any:
        if kwargs.get("stream"):
            return _FakeStream()
        return _FakeResponse("阿司匹林肠溶片，一次 100mg。")


class FakeChat:
    completions = FakeCompletions()


class FakeAsyncOpenAI:
    chat = FakeChat()


class EmptyCompletions:
    @staticmethod
    async def create(**kwargs: Any) -> Any:
        return _FakeResponse(None)


class EmptyAsyncOpenAI:
    class chat:  # noqa: N801
        completions = EmptyCompletions()


async def test_chat_returns_content() -> None:
    provider = _make_provider(FakeAsyncOpenAI())
    answer = await provider.chat([ChatMessage(role="user", content="阿司匹林剂量")])
    assert answer == "阿司匹林肠溶片，一次 100mg。"


async def test_chat_empty_content_raises() -> None:
    provider = _make_provider(EmptyAsyncOpenAI())
    with pytest.raises(ProviderError):
        await provider.chat([ChatMessage(role="user", content="x")])


async def test_chat_stream_yields_deltas() -> None:
    provider = _make_provider(FakeAsyncOpenAI())
    tokens = [t async for t in provider.chat_stream([ChatMessage(role="user", content="hi")])]
    assert tokens == ["你", "好"]
