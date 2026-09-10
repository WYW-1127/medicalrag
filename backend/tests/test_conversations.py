"""会话端点测试：aiosqlite + 注册用户 + 受保护访问。"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.main import app
from app.models import Base


@pytest.fixture
async def client():
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    app.state.session_factory = lambda: factory
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        # 注册并登录拿 token
        await c.post("/api/v1/auth/register", json={"username": "u1", "password": "secret123"})
        token = (
            await c.post("/api/v1/auth/login", json={"username": "u1", "password": "secret123"})
        ).json()["access_token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c
    await engine.dispose()


async def test_conversations_empty_then_created_via_service(client):
    assert (await client.get("/api/v1/conversations")).json() == []
    # 直接走 service 建一条（chat 端点在 T5 覆盖创建链路）
    factory = app.state.session_factory()
    async with factory() as session:
        from app.services import conversations as svc

        conv = await svc.create_conversation(session, user_id=1, title="高血压咨询")
        await svc.append_message(session, conv.id, "user", "血压多高算高？")
        await svc.append_message(
            session, conv.id, "assistant", "标准是收缩压≥140mmHg[1]",
            citations=[{
                "no": 1, "chunk_id": "c1", "source": "g.pdf",
                "section_path": "", "page": 3, "text": "…",
            }],
            latency_ms=1234,
        )
    resp = await client.get("/api/v1/conversations")
    assert len(resp.json()) == 1 and resp.json()[0]["title"] == "高血压咨询"

    msgs = (await client.get(f"/api/v1/conversations/{conv.id}/messages")).json()
    assert len(msgs) == 2
    assert msgs[1]["citations"][0]["source"] == "g.pdf"
    assert msgs[1]["latency_ms"] == 1234


async def test_conversation_isolation_between_users(client):
    factory = app.state.session_factory()
    async with factory() as session:
        from app.services import conversations as svc

        await svc.create_conversation(session, user_id=999, title="别人的会话")
    convs = (await client.get("/api/v1/conversations")).json()
    assert convs == []  # 用户 1 看不到用户 999 的会话


async def test_messages_404_for_other_user(client):
    factory = app.state.session_factory()
    async with factory() as session:
        from app.services import conversations as svc

        conv = await svc.create_conversation(session, user_id=999, title="x")
    resp = await client.get(f"/api/v1/conversations/{conv.id}/messages")
    assert resp.status_code == 404


async def test_unauthorized_rejected(client):
    resp = await client.get(
        "/api/v1/conversations", headers={"Authorization": ""}
    )
    assert resp.status_code == 401
