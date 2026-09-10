import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Base, Conversation, IngestJob, Message, User


@pytest.fixture
async def session():  # type: ignore[no-untyped-def]
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def test_conversation_with_messages_roundtrip(session) -> None:  # type: ignore[no-untyped-def]
    user = User(username="alice", password_hash="hashed")
    session.add(user)
    await session.flush()

    conv = Conversation(user_id=user.id, title="高血压用药咨询")
    session.add(conv)
    await session.flush()

    session.add(Message(conversation_id=conv.id, role="user", content="阿司匹林每天吃多少？"))
    session.add(
        Message(
            conversation_id=conv.id,
            role="assistant",
            content="根据指南……",
            citations=[{"chunk_id": "c-1", "source": "冠心病指南", "page": 12}],
            latency_ms=1234,
        )
    )
    await session.commit()

    msgs = (
        (await session.execute(select(Message).where(Message.conversation_id == conv.id)))
        .scalars()
        .all()
    )
    assert len(msgs) == 2
    assert msgs[1].citations[0]["source"] == "冠心病指南"
    assert msgs[1].latency_ms == 1234


async def test_ingest_job_defaults(session) -> None:  # type: ignore[no-untyped-def]
    job = IngestJob(status="pending")
    session.add(job)
    await session.commit()
    stored = (await session.execute(select(IngestJob))).scalars().one()
    assert stored.status == "pending"
    assert stored.total_docs == 0
    assert stored.error is None
