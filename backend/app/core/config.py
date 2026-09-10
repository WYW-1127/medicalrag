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


class ChunkingSettings(BaseModel):
    strategy: str = "structural"  # structural | fixed | recursive（P7 消融用）
    max_chars: int = 600
    min_chars: int = 100
    overlap: int = 80
    table_max_chars: int = 4000


class RetrievalSettings(BaseModel):
    recall_k: int = 50  # 每路召回数量
    rerank_k: int = 30  # 送入重排的融合结果数
    top_k: int = 8  # 最终返回
    fusion: str = "rrf"  # rrf | weighted（P7 消融用）
    rrf_k: int = 60  # RRF 平滑常数
    dense_weight: float = 0.5
    sparse_weight: float = 0.5


class AgentSettings(BaseModel):
    max_rewrite_iterations: int = 2  # grade 失败重写上限
    max_regenerate: int = 1  # verify 失败再生成上限
    grade_threshold: float = 0.4  # chunk 相关性阈值
    grade_min_relevant: int = 2  # 有效相关 chunk 最少数量
    subquery_max: int = 3  # 多跳拆解子查询上限


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
    milvus_collection: str = "medical_chunks"

    llm: LLMSettings = LLMSettings()
    embedding: EmbeddingSettings = EmbeddingSettings()
    reranker: RerankerSettings = RerankerSettings()
    chunking: ChunkingSettings = ChunkingSettings()
    retrieval: RetrievalSettings = RetrievalSettings()
    agent: AgentSettings = AgentSettings()


@lru_cache
def get_settings() -> Settings:
    return Settings()
