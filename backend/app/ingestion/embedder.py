from loguru import logger

from app.core.providers import get_embedding_provider
from app.core.providers.embedding import EmbeddingProvider


class EmbeddingBatcher:
    """文本批量向量化：按 batch_size 分批调用（对齐 API 单批上限），保序返回。"""

    def __init__(
        self, provider: EmbeddingProvider | None = None, batch_size: int = 32
    ) -> None:
        self._provider = provider or get_embedding_provider()
        self._batch_size = batch_size

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        total = len(texts)
        for start in range(0, total, self._batch_size):
            batch = texts[start : start + self._batch_size]
            vectors.extend(await self._provider.embed(batch))
            logger.info(
                "embedding 进度 {}/{}", min(start + self._batch_size, total), total
            )
        return vectors
