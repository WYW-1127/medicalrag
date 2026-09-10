from collections.abc import AsyncIterator
from typing import Literal, cast

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel

from app.core.config import LLMSettings


class ProviderError(Exception):
    """模型提供方业务性失败（空内容、异常响应等）。"""


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMProvider:
    """OpenAI 兼容 Chat 客户端。超时与网络重试由 openai SDK 内置（max_retries）。"""

    def __init__(self, settings: LLMSettings, client: AsyncOpenAI | None = None) -> None:
        self._settings = settings
        self._client = client or AsyncOpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key,
            timeout=settings.timeout,
            max_retries=settings.max_retries,
        )

    def _to_params(self, messages: list[ChatMessage]) -> list[ChatCompletionMessageParam]:
        return cast(list[ChatCompletionMessageParam], [m.model_dump() for m in messages])

    async def chat(
        self, messages: list[ChatMessage], *, temperature: float | None = None
    ) -> str:
        resp = await self._client.chat.completions.create(
            model=self._settings.model,
            messages=self._to_params(messages),
            temperature=self._settings.temperature if temperature is None else temperature,
        )
        content = resp.choices[0].message.content
        if content is None:
            raise ProviderError("LLM 返回空内容")
        return content

    async def chat_stream(
        self, messages: list[ChatMessage], *, temperature: float | None = None
    ) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=self._settings.model,
            messages=self._to_params(messages),
            temperature=(
                self._settings.temperature if temperature is None else temperature
            ),
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
