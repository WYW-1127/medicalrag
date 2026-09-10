from openai import AsyncOpenAI, AuthenticationError
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from app.core.config import EmbeddingSettings


class EmbeddingProvider:
    """OpenAI 兼容 /embeddings 端点（SiliconFlow BGE-M3）。

    网关偶发以 400+HTML 形式返回瞬时错误（限流/抖动），除鉴权失败外重试。
    """

    def __init__(
        self, settings: EmbeddingSettings, client: AsyncOpenAI | None = None
    ) -> None:
        self._settings = settings
        self._client = client or AsyncOpenAI(
            base_url=settings.base_url, api_key=settings.api_key, timeout=30.0, max_retries=3
        )

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=15),
        retry=retry_if_not_exception_type(AuthenticationError),
        reraise=True,
    )
    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = await self._client.embeddings.create(
            model=self._settings.model, input=texts
        )
        return [item.embedding for item in resp.data]
