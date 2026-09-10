from functools import lru_cache

from app.core.config import get_settings
from app.core.providers.embedding import EmbeddingProvider
from app.core.providers.llm import LLMProvider
from app.core.providers.reranker import RerankerProvider


@lru_cache
def get_llm_provider() -> LLMProvider:
    return LLMProvider(get_settings().llm)


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    return EmbeddingProvider(get_settings().embedding)


@lru_cache
def get_reranker_provider() -> RerankerProvider:
    return RerankerProvider(get_settings().reranker)
