from openai import AsyncOpenAI

from app.core.config import EmbeddingSettings


class EmbeddingProvider:
    """OpenAI 兼容 /embeddings 端点（SiliconFlow BGE-M3）。"""

    def __init__(
        self, settings: EmbeddingSettings, client: AsyncOpenAI | None = None
    ) -> None:
        self._settings = settings
        self._client = client or AsyncOpenAI(
            base_url=settings.base_url, api_key=settings.api_key, timeout=30.0, max_retries=3
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = await self._client.embeddings.create(
            model=self._settings.model, input=texts
        )
        return [item.embedding for item in resp.data]
