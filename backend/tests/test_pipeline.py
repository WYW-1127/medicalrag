from pathlib import Path
from typing import Any

from app.ingestion.embedder import EmbeddingBatcher
from app.ingestion.pipeline import run_ingestion, scan_files


class FakeStore:
    def __init__(self) -> None:
        self.docs: list[tuple[str, str, int]] = []
        self.recreated = False

    def ensure_collection(self, recreate: bool = False) -> None:
        self.recreated = recreate

    def upsert_document(self, meta: Any, rows: list[dict]) -> int:
        self.docs.append((meta.doc_hash, meta.department, len(rows)))
        return len(rows)


class FakeBatcher(EmbeddingBatcher):
    def __init__(self) -> None:
        pass

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


def _data(tmp_path: Path) -> Path:
    d = tmp_path / "raw" / "markdown" / "心血管"
    d.mkdir(parents=True)
    (d / "g.md").write_text(
        "# 指南\n\n## 一\n\n内容A。\n\n## 二\n\n内容B。", encoding="utf-8"
    )
    (tmp_path / "raw" / "ignored.txt").write_text("skip", encoding="utf-8")
    return tmp_path / "raw"


def test_scan_filters_suffixes(tmp_path: Path):
    files = scan_files(_data(tmp_path))
    assert [f.name for f in files] == ["g.md"]


async def test_run_ingestion_dry_run(tmp_path: Path):
    stats = await run_ingestion(_data(tmp_path), dry_run=True)
    assert stats.total_docs == 1
    assert stats.processed_docs == 1
    assert stats.total_chunks >= 2
    assert not stats.errors


async def test_run_ingestion_with_fakes(tmp_path: Path):
    store, batcher = FakeStore(), FakeBatcher()
    stats = await run_ingestion(
        _data(tmp_path), store=store, batcher=batcher  # type: ignore[arg-type]
    )
    assert stats.processed_docs == 1
    assert not stats.errors
    assert store.docs and store.docs[0][1] == "心血管"  # 科室来自子目录
    assert store.docs[0][2] == stats.total_chunks
    assert store.recreated is False


async def test_run_ingestion_recreate_flag(tmp_path: Path):
    store = FakeStore()
    await run_ingestion(
        _data(tmp_path), store=store, batcher=FakeBatcher(), recreate=True  # type: ignore[arg-type]
    )
    assert store.recreated is True
