from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.config import get_settings
from app.ingestion.chunking import chunk_document
from app.ingestion.embedder import EmbeddingBatcher
from app.ingestion.models import ParsedDocument
from app.ingestion.parsers import get_parser
from app.ingestion.registry import department_for
from app.ingestion.store import DocumentMeta, MilvusStore

SUPPORTED_SUFFIXES = {".pdf", ".md", ".markdown", ".html", ".htm", ".docx", ".json", ".csv"}


@dataclass
class IngestStats:
    total_docs: int = 0
    processed_docs: int = 0
    total_chunks: int = 0
    errors: list[str] = field(default_factory=list)


def scan_files(root: Path) -> list[Path]:
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file()
        and p.suffix.lower() in SUPPORTED_SUFFIXES
        and p.name.upper() != "README.MD"  # 目录说明文件不是语料
    )


def parse_file(path: Path, data_root: Path) -> ParsedDocument:
    return get_parser(path).parse(
        path, department=department_for(path, data_root), source_path=str(path)
    )


async def run_ingestion(
    data_root: Path,
    *,
    strategy: str | None = None,
    dry_run: bool = False,
    limit: int | None = None,
    recreate: bool = False,
    store: Any | None = None,
    batcher: EmbeddingBatcher | None = None,
) -> IngestStats:
    """编排：扫描 → 解析 → 分块 →（向量化 → Milvus upsert）。单文件失败不中断。"""
    settings = get_settings()
    files = scan_files(data_root)
    if limit:
        files = files[:limit]
    stats = IngestStats(total_docs=len(files))

    chunk_cfg = (
        settings.chunking.model_copy(update={"strategy": strategy})
        if strategy
        else settings.chunking
    )

    if dry_run:
        for f in files:
            try:
                doc = parse_file(f, data_root)
                n = len(chunk_document(doc, chunk_cfg))
                stats.processed_docs += 1
                stats.total_chunks += n
                logger.info("[dry-run] {} -> {} chunks", f.name, n)
            except Exception as exc:
                stats.errors.append(f"{f}: {exc}")
                logger.error("解析失败 {}: {}", f, exc)
        return stats

    active_store = store or MilvusStore(settings.milvus_uri, settings.milvus_collection)
    active_batcher = batcher or EmbeddingBatcher()
    active_store.ensure_collection(recreate=recreate)

    for f in files:
        try:
            doc = parse_file(f, data_root)
            chunks = chunk_document(doc, chunk_cfg)
            vectors = await active_batcher.embed([c.text for c in chunks])
            rows = [
                {
                    "chunk_id": c.chunk_id,
                    "text": c.text[:8000],  # Milvus varchar 上限 8192 的最后防线
                    "dense": v,
                    "section_path": c.section_path or "",
                    "page": c.page or 0,
                    "seq": c.seq,
                }
                for c, v in zip(chunks, vectors, strict=True)
            ]
            meta = DocumentMeta(
                doc_hash=doc.doc_hash, doc_type=doc.doc_type,
                department=doc.department, source=doc.source_path,
            )
            n = active_store.upsert_document(meta, rows)
            stats.processed_docs += 1
            stats.total_chunks += n
            logger.info("入库 {}（{}）-> {} chunks", f.name, doc.department, n)
            await _record_document(doc.title, n, meta)
        except Exception as exc:
            stats.errors.append(f"{f}: {exc}")
            logger.exception("处理失败 {}", f)

    await _record_job(stats)
    return stats


async def _record_job(stats: IngestStats) -> None:
    """IngestJob 落库；MySQL 不可用时降级为 warning（入库本身不依赖 MySQL）。"""
    try:
        from app.core.db import get_session_factory
        from app.models import IngestJob

        settings = get_settings()
        factory = get_session_factory(settings.database_url)
        async with factory() as session:
            session.add(
                IngestJob(
                    status="failed" if stats.errors else "completed",
                    total_docs=stats.total_docs,
                    processed_docs=stats.processed_docs,
                    total_chunks=stats.total_chunks,
                    error="; ".join(stats.errors[:5]) or None,
                )
            )
            await session.commit()
    except Exception as exc:
        logger.warning("IngestJob 记录失败（忽略）: {}", exc)


async def _record_document(title: str, chunk_count: int, meta: DocumentMeta) -> None:
    """文档登记（documents 表）；按 doc_hash 幂等更新。MySQL 不可用时降级 warning。"""
    try:
        from sqlalchemy import select

        from app.core.db import get_session_factory
        from app.models import Document

        settings = get_settings()
        factory = get_session_factory(settings.database_url)
        async with factory() as session:
            existing = (
                (
                    await session.execute(
                        select(Document).where(Document.doc_hash == meta.doc_hash)
                    )
                )
                .scalars()
                .one_or_none()
            )
            if existing is not None:
                existing.title = title
                existing.chunk_count = chunk_count
            else:
                session.add(
                    Document(
                        doc_hash=meta.doc_hash,
                        source=meta.source,
                        title=title,
                        doc_type=meta.doc_type,
                        department=meta.department,
                        chunk_count=chunk_count,
                    )
                )
            await session.commit()
    except Exception as exc:
        logger.warning("Document 登记失败（忽略）: {}", exc)
