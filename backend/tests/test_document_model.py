from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.ingestion.store import DocumentMeta
from app.models import Base, Document


@pytest.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_document_model_roundtrip(session_factory):
    async with session_factory() as s:
        s.add(Document(doc_hash="a" * 16, source="x.pdf", title="指南",
                       doc_type="guideline", department="心血管", chunk_count=10))
        await s.commit()
    async with session_factory() as s:
        doc = (await s.execute(select(Document))).scalars().one()
        assert doc.chunk_count == 10 and doc.department == "心血管"


async def test_record_document_idempotent(session_factory, monkeypatch):
    """_record_document 按 doc_hash 幂等：重复登记更新而非新增。"""
    import app.ingestion.pipeline as pipeline_mod

    def fake_get_factory(url: str) -> Any:  # 同步：get_session_factory 本身是同步工厂的工厂
        return session_factory

    import app.core.db as db_mod

    monkeypatch.setattr(db_mod, "get_session_factory", fake_get_factory)

    meta = DocumentMeta("a" * 16, "guideline", "心血管", "x.pdf")
    await pipeline_mod._record_document("高血压指南", 12, meta)  # noqa: SLF001
    await pipeline_mod._record_document("高血压指南(修订)", 15, meta)  # noqa: SLF001

    async with session_factory() as s:
        docs = (await s.execute(select(Document))).scalars().all()
        assert len(docs) == 1
        assert docs[0].chunk_count == 15
        assert docs[0].title == "高血压指南(修订)"


def test_document_in_models_export():
    from app.models import __all__ as exported

    assert "Document" in exported
