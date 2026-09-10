from functools import lru_cache

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseModel):
    base_url: str = "https://api.deepseek.com/v1"
    api_key: str = ""
    model: str = "deepseek-chat"
    temperature: float = 0.3
    timeout: float = 60.0
    max_retries: int = 3


class EmbeddingSettings(BaseModel):
    base_url: str = "https://api.siliconflow.cn/v1"
    api_key: str = ""
    model: str = "BAAI/bge-m3"
    dimensions: int = 1024


class RerankerSettings(BaseModel):
    base_url: str = "https://api.siliconflow.cn/v1"
    api_key: str = ""
    model: str = "BAAI/bge-reranker-v2-m3"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_nested_delimiter="__", extra="ignore"
    )

    app_name: str = "MedicalRAG"
    debug: bool = False
    api_prefix: str = "/api/v1"
    jwt_secret: str = "change-me"  # noqa: S105 —— 开发占位默认值，生产由 .env 注入
    jwt_expire_minutes: int = 60 * 24 * 7

    database_url: str = "mysql+asyncmy://root:medicalrag@localhost:3307/medicalrag"
    redis_url: str = "redis://localhost:6380/0"
    milvus_uri: str = "http://localhost:19530"

    llm: LLMSettings = LLMSettings()
    embedding: EmbeddingSettings = EmbeddingSettings()
    reranker: RerankerSettings = RerankerSettings()


@lru_cache
def get_settings() -> Settings:
    return Settings()
