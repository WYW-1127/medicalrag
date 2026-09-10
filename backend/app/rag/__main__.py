import argparse
import asyncio
import sys
from typing import Any

# Windows 控制台默认 GBK，强制 UTF-8 避免中文乱码
_stdout: Any = sys.stdout
if _stdout.encoding and _stdout.encoding.lower() != "utf-8":
    _stdout.reconfigure(encoding="utf-8")

from app.core.logging import setup_logging  # noqa: E402
from app.rag.models import RetrievalResult  # noqa: E402
from app.rag.retriever import HybridRetriever  # noqa: E402


def _show(tag: str, chunks: list[Any], score_field: str) -> None:
    print(f"== {tag} ==")
    for i, c in enumerate(chunks, 1):
        score = getattr(c, score_field) or 0.0
        text = c.text[:48].replace("\n", " ")
        print(f"  {i:2d}. {score:.4f} [{c.department}|{c.section_path[:26]}] {text}")


def _print(result: RetrievalResult, use_rerank: bool) -> None:
    print(f"查询: {result.query}")
    for t in result.timings:
        print(f"  [{t.name}] {t.ms:.0f}ms")
    print(f"召回: dense {result.recalled_dense} / sparse {result.recalled_sparse}")
    _show("融合后 top10", result.fused[:10], "fused_score")
    _show(
        "最终结果（重排后）" if use_rerank else "最终结果（未重排）",
        result.final,
        "rerank_score" if use_rerank else "fused_score",
    )


def main() -> int:
    ap = argparse.ArgumentParser(prog="app.rag", description="MedicalRAG 检索调试")
    ap.add_argument("--q", required=True, help="查询文本")
    ap.add_argument("--fusion", choices=["rrf", "weighted"], default=None)
    ap.add_argument("--no-rerank", action="store_true", help="跳过重排")
    ap.add_argument("--department", default=None, help="科室过滤，如 心血管")
    ap.add_argument("--doc-type", default=None, help="文档类型过滤，如 guideline")
    ap.add_argument("--top-k", type=int, default=None)
    args = ap.parse_args()

    setup_logging()

    async def _run() -> RetrievalResult:
        retriever = HybridRetriever()
        return await retriever.retrieve(
            args.q,
            top_k=args.top_k,
            fusion=args.fusion,
            department=args.department,
            doc_type=args.doc_type,
            use_rerank=not args.no_rerank,
        )

    try:
        result = asyncio.run(_run())
    except Exception as exc:
        print(f"检索失败: {exc}", file=sys.stderr)
        return 1
    _print(result, use_rerank=not args.no_rerank)
    return 0


if __name__ == "__main__":
    sys.exit(main())
