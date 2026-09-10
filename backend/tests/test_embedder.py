from app.core.providers.embedding import EmbeddingProvider
from app.ingestion.embedder import EmbeddingBatcher


class SeqProvider(EmbeddingProvider):
    """按批记录数量、每批返回批内序号向量的假 provider。"""

    def __init__(self) -> None:
        self.batches: list[int] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.batches.append(len(texts))
        return [[float(i)] for i in range(len(texts))]


async def test_batches_preserve_order():
    p = SeqProvider()
    batcher = EmbeddingBatcher(provider=p, batch_size=4)
    vecs = await batcher.embed([f"t{i}" for i in range(10)])
    assert p.batches == [4, 4, 2]
    # 每批内部序号从 0 递增，跨批拼接后与文本顺序一一对应
    assert [v[0] for v in vecs] == [0, 1, 2, 3, 0, 1, 2, 3, 0, 1]


async def test_empty_input():
    batcher = EmbeddingBatcher(provider=SeqProvider(), batch_size=4)
    assert await batcher.embed([]) == []


async def test_small_input_single_batch():
    p = SeqProvider()
    batcher = EmbeddingBatcher(provider=p, batch_size=32)
    await batcher.embed(["a", "b"])
    assert p.batches == [2]
