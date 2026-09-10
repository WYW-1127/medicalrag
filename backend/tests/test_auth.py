"""认证端点测试：aiosqlite 内存库注入 app.state.session_factory。"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token
from app.main import app
from app.models import Base


@pytest.fixture
async def auth_client():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    app.state.session_factory = lambda: factory
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    await engine.dispose()


async def test_register_login_flow(auth_client):
    resp = await auth_client.post(
        "/api/v1/auth/register", json={"username": "alice", "password": "secret123"}
    )
    assert resp.status_code == 201
    assert resp.json()["username"] == "alice"

    resp = await auth_client.post(
        "/api/v1/auth/login", json={"username": "alice", "password": "secret123"}
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    assert token

    # 错误密码
    resp = await auth_client.post(
        "/api/v1/auth/login", json={"username": "alice", "password": "wrong-pass"}
    )
    assert resp.status_code == 401


async def test_register_duplicate_username(auth_client):
    payload = {"username": "bob", "password": "secret123"}
    assert (await auth_client.post("/api/v1/auth/register", json=payload)).status_code == 201
    assert (await auth_client.post("/api/v1/auth/register", json=payload)).status_code == 409


def test_password_hash_and_token_roundtrip():
    from app.core.security import decode_token, hash_password, verify_password

    h = hash_password("secret123")
    assert verify_password("secret123", h)
    assert not verify_password("wrong", h)
    assert decode_token(create_access_token("alice")) == "alice"
    assert decode_token("not-a-jwt") is None
