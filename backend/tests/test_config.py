from app.core.config import Settings


def test_settings_defaults() -> None:
    s = Settings(_env_file=None)
    assert s.llm.model == "deepseek-chat"
    assert s.llm.temperature == 0.3
    assert s.embedding.model == "BAAI/bge-m3"
    assert s.embedding.dimensions == 1024
    assert s.reranker.model == "BAAI/bge-reranker-v2-m3"
    assert s.api_prefix == "/api/v1"


def test_settings_env_override_nested() -> None:
    import os

    os.environ["LLM__API_KEY"] = "sk-test-123"
    os.environ["LLM__MODEL"] = "glm-4-flash"
    os.environ["LLM__BASE_URL"] = "https://open.bigmodel.cn/api/paas/v4"
    try:
        s = Settings(_env_file=None)
        assert s.llm.api_key == "sk-test-123"
        assert s.llm.model == "glm-4-flash"
        assert s.llm.base_url == "https://open.bigmodel.cn/api/paas/v4"
    finally:
        del os.environ["LLM__API_KEY"]
        del os.environ["LLM__MODEL"]
        del os.environ["LLM__BASE_URL"]
