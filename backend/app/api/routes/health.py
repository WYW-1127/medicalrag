import asyncio

from fastapi import APIRouter
from pymilvus import MilvusClient
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import get_engine

router = APIRouter(tags=["health"])


async def check_mysql() -> bool:
    try:
        engine = get_engine(get_settings().database_url)
        async with asyncio.timeout(3), engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def check_redis() -> bool:
    try:
        client = Redis.from_url(get_settings().redis_url)
        async with asyncio.timeout(3):
            await client.ping()
        await client.aclose()
        return True
    except Exception:
        return False


def check_milvus() -> bool:
    """pymilvus 是同步 SDK，由路由层放到线程池执行。"""
    try:
        client = MilvusClient(uri=get_settings().milvus_uri)
        client.get_server_version()
        client.close()
        return True
    except Exception:
        return False


@router.get("/health")
async def health() -> dict[str, object]:
    checks: dict[str, bool] = {
        "mysql": await check_mysql(),
        "redis": await check_redis(),
        "milvus": await asyncio.to_thread(check_milvus),
    }
    status = "ok" if all(checks.values()) else "degraded"
    return {
        "status": status,
        "checks": {name: "ok" if ok else "unreachable" for name, ok in checks.items()},
    }
