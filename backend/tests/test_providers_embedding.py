from app.core.config import EmbeddingSettings
from app.core.providers.embedding import EmbeddingProvider


class _Item:
    def __init__(self, vector: list[float]) -> None:
        self.embedding = vector


class _Data:
    def __init__(self, vectors: list[list[float]]) -> None:
        self.data = [_Item(v) for v in vectors]


class FakeEmbeddings:
    def __init__(self) -> None:
        self.received_input: list[str] | None = None

    async def create(self, **kwargs):  # type: ignore[no-untyped-def]
        self.received_input = kwargs["input"]
        return _Data([[0.1, 0.2], [0.3, 0.4]])


class FakeAsyncOpenAI:
    def __init__(self, embeddings: FakeEmbeddings) -> None:
        self.embeddings = embeddings


async def test_embed_returns_vectors_in_order() -> None:
    fake = FakeEmbeddings()
    provider = EmbeddingProvider(EmbeddingSettings(api_key="sk-test"), client=FakeAsyncOpenAI(fake))  # type: ignore[arg-type]
    vectors = await provider.embed(["高血压指南", "糖尿病指南"])
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert fake.received_input == ["高血压指南", "糖尿病指南"]


async def test_embed_empty_input_short_circuits() -> None:
    fake = FakeEmbeddings()
    provider = EmbeddingProvider(EmbeddingSettings(api_key="sk-test"), client=FakeAsyncOpenAI(fake))  # type: ignore[arg-type]
    assert await provider.embed([]) == []
    assert fake.received_input is None
