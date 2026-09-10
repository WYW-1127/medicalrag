from app.core.config import ChunkingSettings
from app.ingestion.chunking import chunk_document
from app.ingestion.models import ParsedDocument, Section


def _doc():
    s21 = Section(level=2, title="用法用量", text="口服。" * 300)  # 900 字
    return ParsedDocument(
        source_path="x",
        doc_type="drug_label",
        department="心血管",
        title="药",
        doc_hash="a" * 16,
        sections=[
            Section(
                level=1,
                title="阿司匹林",
                children=[
                    Section(level=2, title="适应证", text="预防心肌梗死。"),
                    s21,
                    Section(
                        level=2,
                        title="剂量表",
                        is_table=True,
                        text="|药|量|\n|---|---|\n|A|100|",
                    ),
                ],
            )
        ],
    )


def test_structural_keeps_path_and_table():
    chunks = chunk_document(_doc(), ChunkingSettings(strategy="structural"))
    assert any("适应证" in c.section_path for c in chunks)
    assert any(c.text.startswith("|药|量|") for c in chunks)
    longs = [c for c in chunks if "用法用量" in c.section_path and "口服" in c.text]
    assert len(longs) >= 2
    assert all(len(c.text) <= 700 for c in longs)
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))


def test_structural_overlap_between_chunks():
    chunks = chunk_document(_doc(), ChunkingSettings(strategy="structural", overlap=30))
    longs = [c for c in chunks if "用法用量" in c.section_path and "口服" in c.text]
    assert len(longs) >= 2
    # 后块以前块尾部 overlap 字符开头（跨块上下文衔接）
    assert longs[1].text.startswith(longs[0].text[-30:])


def test_fixed_strategy_flat_window():
    chunks = chunk_document(
        _doc(), ChunkingSettings(strategy="fixed", max_chars=200, overlap=50)
    )
    assert all(len(c.text) <= 200 for c in chunks)
    assert chunks[0].section_path == ""  # 基线无结构信息
    assert len(chunks) >= 5  # 拍平全文（>1000 字）切成多块


def test_recursive_strategy_respects_max():
    chunks = chunk_document(_doc(), ChunkingSettings(strategy="recursive", max_chars=300))
    assert chunks
    assert all(len(c.text) <= 320 for c in chunks)


def test_small_tail_merged():
    chunks = chunk_document(_doc(), ChunkingSettings(strategy="structural"))
    texts = [c.text for c in chunks if "预防心肌梗死" in c.text]
    assert len(texts) == 1  # 短文本不单独成块


def test_unknown_strategy_raises():
    try:
        chunk_document(_doc(), ChunkingSettings(strategy="nope"))
        raise AssertionError("should raise ValueError")
    except ValueError:
        pass
