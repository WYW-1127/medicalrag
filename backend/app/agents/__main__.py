import argparse
import asyncio
import sys
from typing import Any

# Windows 控制台默认 GBK，强制 UTF-8 避免中文乱码
_stdout: Any = sys.stdout
if _stdout.encoding and _stdout.encoding.lower() != "utf-8":
    _stdout.reconfigure(encoding="utf-8")

from app.agents.graph import MedicalRAGAgent  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(prog="app.agents", description="MedicalRAG Agentic 问答")
    ap.add_argument("--q", required=True, help="用户问题")
    args = ap.parse_args()

    setup_logging()

    async def _run() -> None:
        agent = MedicalRAGAgent()
        result = await agent.run(args.q)
        print(f"\n{'=' * 60}")
        print(f"路由: {result.route}")
        print(f"{'=' * 60}\n【回答】\n{result.answer}")
        if result.citations:
            print("\n【引用】")
            for c in result.citations:
                print(f"  [{c['no']}] {c['source']}｜{c['section_path'] or '无章节'}｜P{c['page']}")
                print(f"      {c['text'][:80]}…")
        print("\n【执行时间线】")
        for s in result.steps:
            print(f"  {s.name:<12} {s.ms:>7.0f}ms  {s.detail}")

    asyncio.run(_run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
