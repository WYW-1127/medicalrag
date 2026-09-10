"""模型 API 连通性检查：LLM / Embedding / Reranker 各真实调用一次。

用法（仓库根目录）：make check-models
前置：backend/.env 已填入真实 key（未填的项会显示 [skip]）。
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402


def _key_ready(key: str) -> bool:
    return bool(key) and "your" not in key


async def check_llm() -> bool:
    from app.core.providers.llm import ChatMessage, LLMProvider

    s = get_settings().llm
    if not _key_ready(s.api_key):
        print(f"[skip] llm   ({s.model}): LLM__API_KEY 未配置")
        return False
    provider = LLMProvider(s)
    start = time.perf_counter()
    try:
        answer = await provider.chat(
            [ChatMessage(role="user", content='只回复两个字："正常"')], temperature=0.0
        )
        ms = (time.perf_counter() - start) * 1000
        print(f"[ok]   llm   ({s.model}): {ms:.0f}ms -> {answer[:30]}")
        return True
    except Exception as exc:
        print(f"[fail] llm   ({s.model}): {exc}")
        return False


async def check_embedding() -> bool:
    from app.core.providers.embedding import EmbeddingProvider

    s = get_settings().embedding
    if not _key_ready(s.api_key):
        print(f"[skip] embed ({s.model}): EMBEDDING__API_KEY 未配置")
        return False
    provider = EmbeddingProvider(s)
    start = time.perf_counter()
    try:
        vectors = await provider.embed(["高血压的一线治疗药物"])
        ms = (time.perf_counter() - start) * 1000
        dim = len(vectors[0])
        assert dim == s.dimensions, f"维度不符：期望 {s.dimensions}，实际 {dim}"
        print(f"[ok]   embed ({s.model}): {ms:.0f}ms, dim={dim}")
        return True
    except Exception as exc:
        print(f"[fail] embed ({s.model}): {exc}")
        return False


async def check_reranker() -> bool:
    from app.core.providers.reranker import RerankerProvider

    s = get_settings().reranker
    if not _key_ready(s.api_key):
        print(f"[skip] rerank({s.model}): RERANKER__API_KEY 未配置")
        return False
    provider = RerankerProvider(s)
    start = time.perf_counter()
    try:
        results = await provider.rerank(
            "阿司匹林的剂量",
            ["阿司匹林肠溶片说明书：一次 100mg", "感冒灵颗粒说明书"],
        )
        ms = (time.perf_counter() - start) * 1000
        assert results and results[0].index == 0, "重排结果不符合预期（相关文档应排第一）"
        print(f"[ok]   rerank({s.model}): {ms:.0f}ms, top_score={results[0].score:.3f}")
        return True
    except Exception as exc:
        print(f"[fail] rerank({s.model}): {exc}")
        return False


async def main() -> int:
    results = await asyncio.gather(check_llm(), check_embedding(), check_reranker())
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
