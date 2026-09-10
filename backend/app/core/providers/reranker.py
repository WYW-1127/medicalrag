import httpx
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import RerankerSettings


class RerankerError(Exception):
    """rerank API 不可恢复错误（非 2xx 或响应结构异常）。"""


class RerankResult(BaseModel):
    index: int
    score: float


class RerankerProvider:
    """SiliconFlow 风格 /rerank 端点（非 OpenAI 标准，走 httpx + tenacity 重试）。"""

    def __init__(
        self, settings: RerankerSettings, client: httpx.AsyncClient | None = None
    ) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(
            base_url=settings.base_url,
            timeout=30.0,
            headers={"Authorization": f"Bearer {settings.api_key}"},
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError)),
        reraise=True,
    )
    async def rerank(self, query: str, documents: list[str]) -> list[RerankResult]:
        if not documents:
            return []
        resp = await self._client.post(
            "/rerank",
            json={"model": self._settings.model, "query": query, "documents": documents},
        )
        if resp.status_code != 200:
            raise RerankerError(f"rerank API 返回 {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        try:
            return [
                RerankResult(index=item["index"], score=item["relevance_score"])
                for item in data["results"]
            ]
        except (KeyError, TypeError) as exc:
            raise RerankerError(f"rerank 响应结构异常: {exc}") from exc
