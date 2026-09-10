from pathlib import Path

from app.ingestion.parsers.markdown import MarkdownParser

SAMPLE = """# 高血压防治指南

## 1. 诊断标准

诊室血压收缩压≥140mmHg 和/或舒张压≥90mmHg。

## 2. 分级

| 分级 | 收缩压 | 舒张压 |
| --- | --- | --- |
| 1级 | 140-159 | 90-99 |
| 2级 | 160-179 | 100-109 |

### 2.1 说明

以上分级适用于未用药状态。

# 附录

参考资料略。
"""


def _parse(tmp_path: Path):
    f = tmp_path / "guide.md"
    f.write_text(SAMPLE, encoding="utf-8")
    return MarkdownParser().parse(
        f, department="心血管", source_path="data/samples/guide.md"
    )


def _iter_all(sections):
    for s in sections:
        yield s
        yield from _iter_all(s.children)


def test_heading_tree_structure(tmp_path: Path):
    doc = _parse(tmp_path)
    assert [s.title for s in doc.sections] == ["高血压防治指南", "附录"]
    ch1 = doc.sections[0].children
    assert [c.title for c in ch1 if not c.is_table] == ["1. 诊断标准", "2. 分级"]
    assert ch1[0].text.startswith("诊室血压")
    # 「2.1 说明」是「2. 分级」的子节点（表格也是）
    assert ch1[1].children[0].title == "表格"
    assert ch1[1].children[1].title == "2.1 说明"


def test_table_kept_as_table_node(tmp_path: Path):
    doc = _parse(tmp_path)
    tables = [s for s in _iter_all(doc.sections) if s.is_table]
    assert len(tables) == 1
    assert "140-159" in tables[0].text
    assert tables[0].text.startswith("|")


def test_doc_metadata(tmp_path: Path):
    doc = _parse(tmp_path)
    assert doc.title == "高血压防治指南"
    assert doc.department == "心血管"
    assert doc.doc_type == "guideline"
    assert len(doc.doc_hash) == 16
