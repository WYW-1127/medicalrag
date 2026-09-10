"""POST /chat SSE 测试：fake agent 注入，验证事件序与消息持久化。"""

import json
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.agents.state import AgentResult, StepEvent
from app.main import app
from app.models import Base, Message


class FakeAgent:
    """脚本化流式 agent：两个 step、三个 token、一个 result。"""

    ANSWER = "高血压的诊断标准是收缩压≥140mmHg[1]。"

    def __init__(self, route: str = "answered") -> None:
        self.route = route
        self.received_query: str | None = None
        self.received_history: list = []

    async def run_streaming(self, query: str, history: list | None = None) -> Any:
        self.received_query = query
        self.received_history = history or []
        yield ("step", StepEvent(name="analyze", ms=10, detail="medical"))
        yield ("step", StepEvent(name="retrieve", ms=20, detail="1 路 → 8 chunks"))
        for i in range(0, len(self.ANSWER), 8):  # 按段流式，拼接等于完整答案
            yield ("token", self.ANSWER[i : i + 8])
        yield (
            "result",
            AgentResult(
                route=self.route,
                answer=self.ANSWER,
                citations=[{"no": 1, "chunk_id": "c1", "text": "…",
                            "source": "g.pdf", "section_path": "诊断", "page": 3}],
                steps=[StepEvent(name="analyze", ms=10)],
            ),
        )


@pytest.fixture
async def sse_client():
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    app.state.session_factory = lambda: factory
    app.state.agent = FakeAgent()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        await c.post("/api/v1/auth/register", json={"username": "ux", "password": "secret123"})
        token = (
            await c.post("/api/v1/auth/login", json={"username": "ux", "password": "secret123"})
        ).json()["access_token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c, app.state.agent
    await engine.dispose()


async def test_chat_sse_event_sequence(sse_client):
    client, _ = sse_client
    resp = await client.post("/api/v1/chat", json={"query": "血压多高算高血压"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    body = resp.text
    # 事件序：step → step → token* → done
    assert body.index("event: step") < body.index("event: token") < body.index("event: done")
    # token 事件拼接等于完整答案
    tokens = []
    for block in body.split("\n\n"):
        if block.startswith("event: token"):
            data_line = next(ln for ln in block.splitlines() if ln.startswith("data: "))
            tokens.append(json.loads(data_line[6:])["text"])
    assert "".join(tokens) == FakeAgent.ANSWER
    # done 事件包含会话与引用
    assert '"conversation_id": 1' in body or '"conversation_id":1' in body
    assert "g.pdf" in body


async def test_chat_persists_messages(sse_client):
    client, _ = sse_client
    await client.post("/api/v1/chat", json={"query": "血压多高算高血压"})
    factory = app.state.session_factory()
    async with factory() as session:
        msgs = (await session.execute(select(Message))).scalars().all()
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[0].content == "血压多高算高血压"
    assert "140mmHg" in msgs[1].content
    assert msgs[1].citations and msgs[1].citations[0]["source"] == "g.pdf"
    assert msgs[1].latency_ms is not None and msgs[1].latency_ms >= 0


async def test_chat_with_existing_conversation_and_history(sse_client):
    client, agent = sse_client
    await client.post("/api/v1/chat", json={"query": "阿司匹林的作用"})
    conv_id = 1
    await client.post(
        "/api/v1/chat", json={"query": "它的剂量呢", "conversation_id": conv_id}
    )
    # 多轮历史传入 agent（指代消解数据源）
    assert agent.received_history, "第二轮对话应携带历史"
    roles = [m.role for m in agent.received_history]
    assert roles == ["user", "assistant"]


async def test_chat_agent_error_yields_error_event(sse_client):
    client, _ = sse_client

    class BrokenAgent:
        async def run_streaming(self, query: str, history: list | None = None) -> Any:
            yield ("step", StepEvent(name="analyze", ms=1, detail="x"))
            raise RuntimeError("Milvus 不可达")

    app.state.agent = BrokenAgent()
    resp = await client.post("/api/v1/chat", json={"query": "q"})
    assert resp.status_code == 200
    assert "event: error" in resp.text
    assert "Milvus 不可达" in resp.text
