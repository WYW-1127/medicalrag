"""知识库管理端点：文档列表（含最近入库任务状态）与按文档采样 chunk。"""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pymilvus import MilvusClient
from sqlalchemy import desc, select

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.models import Document, IngestJob, User

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("")
async def list_documents(
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    factory = request.app.state.session_factory()
    async with factory() as session:
        docs = list(
            (
                await session.execute(select(Document).order_by(desc(Document.updated_at)))
            )
            .scalars()
            .all()
        )
        last_job = (
            (
                await session.execute(
                    select(IngestJob).order_by(desc(IngestJob.id)).limit(1)
                )
            )
            .scalars()
            .one_or_none()
        )
    return {
        "documents": [
            {
                "id": d.id,
                "doc_hash": d.doc_hash,
                "source": Path(d.source).name,
                "title": d.title,
                "doc_type": d.doc_type,
                "department": d.department,
                "chunk_count": d.chunk_count,
                "updated_at": d.updated_at,
            }
            for d in docs
        ],
        "last_ingest_job": (
            None
            if last_job is None
            else {
                "id": last_job.id,
                "status": last_job.status,
                "total_docs": last_job.total_docs,
                "processed_docs": last_job.processed_docs,
                "total_chunks": last_job.total_chunks,
                "error": last_job.error,
                "created_at": last_job.created_at,
            }
        ),
    }


@router.get("/{doc_hash}/chunks")
async def sample_chunks(
    doc_hash: str,
    request: Request,
    k: int = Query(default=3, ge=1, le=10),
    user: User = Depends(get_current_user),  # noqa: B008
) -> list[dict[str, Any]]:
    client: Any = getattr(request.app.state, "milvus_client", None) or MilvusClient(
        uri=get_settings().milvus_uri
    )
    try:
        client.load_collection(get_settings().milvus_collection)
        rows = client.query(
            collection_name=get_settings().milvus_collection,
            filter=f'doc_hash == "{doc_hash}"',
            output_fields=["chunk_id", "text", "section_path", "seq"],
            limit=k,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Milvus 查询失败: {exc}") from exc
    if not rows:
        raise HTTPException(status_code=404, detail="该文档无 chunk（未入库？）")
    return [
        {
            "chunk_id": r["chunk_id"],
            "text": r["text"][:300],
            "section_path": r.get("section_path", ""),
            "seq": r.get("seq", 0),
        }
        for r in rows
    ]
