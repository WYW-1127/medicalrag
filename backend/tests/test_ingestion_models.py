from pathlib import Path

from app.ingestion.models import Chunk, ParsedDocument, Section
from app.ingestion.registry import department_for, doc_type_for, file_hash


def test_doc_type_by_suffix():
    assert doc_type_for(".json") == "drug_label"
    assert doc_type_for(".CSV") == "structured_table"
    assert doc_type_for(".pdf") == "guideline"


def test_department_from_subdir(tmp_path: Path):
    (tmp_path / "pdf" / "心血管").mkdir(parents=True)
    f = tmp_path / "pdf" / "心血管" / "指南.pdf"
    f.touch()
    assert department_for(f, tmp_path) == "心血管"
    (tmp_path / "pdf" / "顶层.pdf").touch()
    assert department_for(tmp_path / "pdf" / "顶层.pdf", tmp_path) == "综合"


def test_file_hash_stable(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("医学", encoding="utf-8")
    assert file_hash(f) == file_hash(f)
    assert len(file_hash(f)) == 16


def test_section_tree_roundtrip():
    root = Section(
        level=1,
        title="指南",
        children=[Section(level=2, title="诊断", text="内容")],
    )
    doc = ParsedDocument(
        source_path="x.md",
        doc_type="guideline",
        department="综合",
        title="指南",
        doc_hash="ab" * 8,
        sections=[root],
    )
    c = Chunk(
        chunk_id="abc-0001",
        doc_hash="ab" * 8,
        text="内容",
        section_path="指南 > 诊断",
        page=None,
        seq=1,
    )
    assert doc.sections[0].children[0].text == c.text
