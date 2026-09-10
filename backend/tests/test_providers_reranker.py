import httpx
import pytest
import respx

from app.core.config import RerankerSettings
from app.core.providers.reranker import RerankerError, RerankerProvider, RerankResult

SETTINGS = RerankerSettings(api_key="sk-test")
URL = "https://api.siliconflow.cn/v1/rerank"


@respx.mock
async def test_rerank_maps_results_in_api_order() -> None:
    route = respx.post(URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.93},
                    {"index": 0, "relevance_score": 0.41},
                ]
            },
        )
    )
    provider = RerankerProvider(SETTINGS)
    results = await provider.rerank("阿司匹林 剂量", ["感冒灵说明书", "阿司匹林肠溶片说明书"])
    assert results == [RerankResult(index=1, score=0.93), RerankResult(index=0, score=0.41)]
    assert route.called
    body = route.calls.last.request.read().decode()
    assert "阿司匹林" in body


@respx.mock
async def test_rerank_empty_documents_no_call() -> None:
    provider = RerankerProvider(SETTINGS)
    assert await provider.rerank("q", []) == []


@respx.mock
async def test_rerank_http_error_raises() -> None:
    respx.post(URL).mock(return_value=httpx.Response(401, json={"error": "bad key"}))
    provider = RerankerProvider(SETTINGS)
    with pytest.raises(RerankerError):
        await provider.rerank("q", ["d1"])
