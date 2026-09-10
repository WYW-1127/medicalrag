"""基础设施连通性检查：MySQL / Redis / Milvus。全部就绪退出码 0，否则 1。

用法（仓库根目录）：make check-infra
依赖 backend 虚拟环境（uv run 提供包）；脚本自身把 backend/ 加进 sys.path。
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402


async def main() -> int:
    settings = get_settings()
    ok = True

    try:
        from sqlalchemy import text

        from app.core.db import get_engine

        engine = get_engine(settings.database_url)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        print("[ok]   mysql")
    except Exception as exc:
        ok = False
        print(f"[fail] mysql: {exc}")

    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.redis_url)
        await client.ping()
        await client.aclose()
        print("[ok]   redis")
    except Exception as exc:
        ok = False
        print(f"[fail] redis: {exc}")

    try:
        from pymilvus import MilvusClient

        client = MilvusClient(uri=settings.milvus_uri)
        client.get_server_version()
        client.close()
        print("[ok]   milvus")
    except Exception as exc:
        ok = False
        print(f"[fail] milvus: {exc}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
