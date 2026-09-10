from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_current_user
from app.models import User
from app.services import conversations as svc

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _session(request: Request) -> Any:
    """返回 session 工厂（app.state.session_factory 是工厂的工厂）。"""
    return request.app.state.session_factory()


@router.get("")
async def list_conversations(
    request: Request, user: User = Depends(get_current_user)  # noqa: B008
) -> list[dict[str, Any]]:
    factory = _session(request)
    async with factory() as session:
        convs = await svc.list_conversations(session, user.id)
    return [
        {"id": c.id, "title": c.title, "created_at": c.created_at, "updated_at": c.updated_at}
        for c in convs
    ]


@router.get("/{conversation_id}/messages")
async def get_messages(
    conversation_id: int,
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
) -> list[dict[str, Any]]:
    factory = _session(request)
    async with factory() as session:
        conv = await svc.get_conversation(session, conversation_id, user.id)
        if conv is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        msgs = await svc.get_messages(session, conversation_id)
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "citations": m.citations,
            "latency_ms": m.latency_ms,
            "created_at": m.created_at,
        }
        for m in msgs
    ]
