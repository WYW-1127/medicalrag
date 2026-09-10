"""documents/admin 端点测试：fake session + fake milvus client。"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.main import app
from app.models import Base, Document, IngestJob


@pytest.fixture
async def client():
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        s.add(Document(doc_hash="a" * 16, source="data/raw/pdf/x/指南.pdf",
                       title="高血压指南", doc_type="guideline",
                       department="心血管", chunk_count=42))
        s.add(IngestJob(status="completed", total_docs=1, processed_docs=1, total_chunks=42))
        await s.commit()

    app.state.session_factory = lambda: factory
    app.state.milvus_client = _FakeMilvus()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        await c.post("/api/v1/auth/register", json={"username": "op", "password": "secret123"})
        token = (
            await c.post("/api/v1/auth/login", json={"username": "op", "password": "secret123"})
        ).json()["access_token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c
    await engine.dispose()


class _FakeMilvus:
    def load_collection(self, name: str) -> None:
        pass

    def query(self, collection_name: str, filter: str, output_fields: list, limit: int):  # type: ignore[no-untyped-def]
        if "a" * 16 not in filter:
            return []
        return [
            {"chunk_id": f"{'a'*12}-0001", "text": "高血压诊断标准正文。",
             "section_path": "指南 > 诊断", "seq": 1},
            {"chunk_id": f"{'a'*12}-0002", "text": "分级正文。", "section_path": "分级", "seq": 2},
        ]


async def test_list_documents_with_last_job(client):
    data = (await client.get("/api/v1/documents")).json()
    assert len(data["documents"]) == 1
    doc = data["documents"][0]
    assert doc["source"] == "指南.pdf"  # 只显示文件名
    assert doc["department"] == "心血管" and doc["chunk_count"] == 42
    assert data["last_ingest_job"]["status"] == "completed"


async def test_sample_chunks(client):
    chunks = (await client.get(f"/api/v1/documents/{'a'*16}/chunks?k=2")).json()
    assert len(chunks) == 2
    assert chunks[0]["section_path"] == "指南 > 诊断"


async def test_sample_chunks_404(client):
    resp = await client.get("/api/v1/documents/unknownhash/chunks")
    assert resp.status_code == 404


async def test_ingest_status_lists_jobs(client):
    jobs = (await client.get("/api/v1/admin/ingest")).json()
    assert len(jobs) == 1 and jobs[0]["total_chunks"] == 42
