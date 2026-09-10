import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

# Windows 控制台默认 GBK，强制 UTF-8 避免中文乱码
_stdout: Any = sys.stdout
if _stdout.encoding and _stdout.encoding.lower() != "utf-8":
    _stdout.reconfigure(encoding="utf-8")

from app.core.logging import setup_logging  # noqa: E402
from app.ingestion.pipeline import run_ingestion  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(prog="app.ingestion", description="MedicalRAG 知识入库管线")
    ap.add_argument("--dir", default="../data/raw", help="数据目录（默认 ../data/raw）")
    ap.add_argument(
        "--strategy", choices=["structural", "fixed", "recursive"], default=None,
        help="分块策略（默认取配置 CHUNKING__STRATEGY）",
    )
    ap.add_argument("--dry-run", action="store_true", help="只解析分块并统计，不写库")
    ap.add_argument("--limit", type=int, default=None, help="只处理前 N 个文件")
    ap.add_argument("--recreate", action="store_true", help="删除并重建 collection")
    args = ap.parse_args()

    setup_logging()
    data_root = Path(args.dir).resolve()
    if not data_root.is_dir():
        print(f"数据目录不存在: {data_root}", file=sys.stderr)
        return 2
    stats = asyncio.run(
        run_ingestion(
            data_root,
            strategy=args.strategy,
            dry_run=args.dry_run,
            limit=args.limit,
            recreate=args.recreate,
        )
    )
    print(
        f"\n完成：{stats.processed_docs}/{stats.total_docs} 文档，"
        f"{stats.total_chunks} chunks，错误 {len(stats.errors)} 个"
    )
    for e in stats.errors[:10]:
        print(f"  - {e}")
    return 0 if not stats.errors else 1


if __name__ == "__main__":
    sys.exit(main())
