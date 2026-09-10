import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import desc, select

from app.api.deps import get_current_user
from app.models import IngestJob, User

router = APIRouter(prefix="/admin", tags=["admin"])


class IngestIn(BaseModel):
    dir: str = "../data/raw"  # 相对 backend 的工作目录


@router.post("/ingest")
async def trigger_ingestion(
    body: IngestIn,
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    from app.ingestion.pipeline import run_ingestion

    data_root = await asyncio.to_thread(lambda: Path(body.dir).resolve())

    async def _run() -> None:
        try:
            await run_ingestion(data_root)
        except Exception:  # noqa: BLE001, S110 失败明细记录在 IngestJob，这里只防任务炸事件循环
            logger.exception("后台入库任务失败")

    running = getattr(request.app.state, "ingest_tasks", [])
    if running and not all(t.done() for t in running):
        return {"started": False, "detail": "已有入库任务在运行"}
    request.app.state.ingest_tasks = [asyncio.create_task(_run())]
    return {"started": True, "dir": str(data_root)}


@router.get("/ingest")
async def ingest_status(
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
) -> list[dict[str, Any]]:
    factory = request.app.state.session_factory()
    async with factory() as session:
        jobs = list(
            (
                await session.execute(
                    select(IngestJob).order_by(desc(IngestJob.id)).limit(10)
                )
            )
            .scalars()
            .all()
        )
    return [
        {
            "id": j.id,
            "status": j.status,
            "total_docs": j.total_docs,
            "processed_docs": j.processed_docs,
            "total_chunks": j.total_chunks,
            "error": j.error,
            "created_at": j.created_at,
        }
        for j in jobs
    ]
