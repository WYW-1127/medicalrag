"""会话领域服务：创建/列表/消息读取/追加（chat 端点与测试共用）。"""

from typing import Any

from sqlalchemy import desc, select

from app.models import Conversation, Message


async def create_conversation(session: Any, user_id: int, title: str) -> Conversation:
    conv = Conversation(user_id=user_id, title=title[:200])
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return conv


async def list_conversations(session: Any, user_id: int) -> list[Conversation]:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(desc(Conversation.updated_at))
        .limit(100)
    )
    return list(result.scalars().all())


async def get_conversation(
    session: Any, conversation_id: int, user_id: int
) -> Conversation | None:
    conv = (
        (
            await session.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
        )
        .scalars()
        .one_or_none()
    )
    if conv is None or conv.user_id != user_id:
        return None
    found: Conversation = conv  # scalars() 返回 Any，显式收窄
    return found


async def get_messages(session: Any, conversation_id: int) -> list[Message]:
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id)
    )
    return list(result.scalars().all())


async def append_message(
    session: Any,
    conversation_id: int,
    role: str,
    content: str,
    citations: list[dict[str, Any]] | None = None,
    latency_ms: int | None = None,
) -> Message:
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        citations=citations,
        latency_ms=latency_ms,
    )
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    return msg
