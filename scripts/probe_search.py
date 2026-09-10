"""检索冒烟：对 medical_chunks 分别做 dense 与 BM25 查询，各打印 top-3。

用法（仓库根目录）：make probe q="阿司匹林剂量"
前置：已入库（make ingest-samples）且 EMBEDDING__API_KEY 可用。
"""
import asyncio
import sys
from pathlib import Path

# Windows 控制台默认 GBK，强制 UTF-8 避免中文乱码
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.core.providers.embedding import EmbeddingProvider  # noqa: E402


async def main() -> int:
    query = sys.argv[1] if len(sys.argv) > 1 else "高血压的诊断标准是什么"
    s = get_settings()
    from pymilvus import MilvusClient

    client = MilvusClient(uri=s.milvus_uri)
    col = s.milvus_collection
    if not client.has_collection(col):
        print(f"collection {col} 不存在，请先入库：make ingest-samples")
        return 2
    client.load_collection(col)

    vec = (await EmbeddingProvider(s.embedding).embed([query]))[0]
    dense_hits = client.search(
        col, data=[vec], anns_field="dense", limit=3,
        output_fields=["text", "section_path", "department"],
        search_params={"metric_type": "COSINE"},
    )
    print("== dense top3 ==")
    for hit in dense_hits[0]:
        ent = hit["entity"]
        print(f"  {hit['distance']:.3f} [{ent['department']}|{ent['section_path']}] {ent['text'][:60]}")

    sparse_hits = client.search(
        col, data=[query], anns_field="sparse", limit=3,
        output_fields=["text", "section_path", "department"],
    )
    print("== BM25 top3 ==")
    for hit in sparse_hits[0]:
        ent = hit["entity"]
        print(f"  {hit['distance']:.3f} [{ent['department']}|{ent['section_path']}] {ent['text'][:60]}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
