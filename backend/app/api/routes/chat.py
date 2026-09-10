"""POST /chat —— SSE 流式问答：step（节点事件）/ token（增量文本）/ done / error。"""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents.streaming import token_sink
from app.api.deps import get_current_user
from app.core.providers.llm import ChatMessage
from app.models import User
from app.services import conversations as svc

router = APIRouter(tags=["chat"])

HISTORY_LIMIT = 10  # 传入 agent 的历史轮数（指代消解上下文）


class ChatIn(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    conversation_id: int | None = None


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat(
    body: ChatIn,
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
) -> StreamingResponse:
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent 未就绪（检查 Milvus 与模型配置）")
    factory = request.app.state.session_factory()

    # 会话解析 + 历史加载 + 用户消息落库
    async with factory() as session:
        if body.conversation_id is not None:
            conv = await svc.get_conversation(session, body.conversation_id, user.id)
            if conv is None:
                raise HTTPException(status_code=404, detail="会话不存在")
            history_msgs = await svc.get_messages(session, conv.id)
        else:
            conv = await svc.create_conversation(session, user.id, title=body.query[:20])
            history_msgs = []
        await svc.append_message(session, conv.id, role="user", content=body.query)
    conversation_id = conv.id
    history = [
        ChatMessage(role=m.role, content=m.content) for m in history_msgs[-HISTORY_LIMIT:]
    ]

    queue: asyncio.Queue[tuple[str, Any] | None] = asyncio.Queue()
    started = time.perf_counter()

    async def produce() -> None:
        def on_token(t: str) -> None:
            queue.put_nowait(("token", t))

        token_sink.set(on_token)
        try:
            async for kind, payload in agent.run_streaming(body.query, history=history):
                await queue.put((kind, payload))
        except Exception as exc:  # noqa: BLE001 错误也要以事件形式到达客户端
            await queue.put(("error", str(exc)))
        finally:
            token_sink.set(None)
            await queue.put(None)

    producer = asyncio.create_task(produce())

    async def event_stream() -> AsyncIterator[str]:
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                kind, payload = item
                if kind == "step":
                    yield _sse("step", payload.model_dump())
                elif kind == "token":
                    yield _sse("token", {"text": payload})
                elif kind == "result":
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    async with factory() as session:
                        msg = await svc.append_message(
                            session, conversation_id, role="assistant",
                            content=payload.answer, citations=payload.citations,
                            latency_ms=latency_ms,
                        )
                    yield _sse(
                        "done",
                        {
                            "route": payload.route,
                            "citations": payload.citations,
                            "conversation_id": conversation_id,
                            "message_id": msg.id,
                            "latency_ms": latency_ms,
                        },
                    )
                elif kind == "error":
                    yield _sse("error", {"message": payload})
        finally:
            if not producer.done():
                producer.cancel()

    return StreamingResponse(event_stream(), media_type="text/event-stream")
