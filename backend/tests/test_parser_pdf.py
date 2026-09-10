from pathlib import Path

import fitz

from app.ingestion.parsers.pdf import PdfParser


def _make_pdf(tmp_path: Path) -> Path:
    p = tmp_path / "demo.pdf"
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for text, size in [
        ("中国高血压临床实践指南", 18),
        ("1 诊断标准", 14),
        ("诊室血压SBP≥140mmHg和/或DBP≥90mmHg可诊断高血压。", 10.5),
        ("在未使用降压药的情况下，非同日三次测量均达到上述标准。", 10.5),
        ("2 治疗原则", 14),
        ("生活方式干预是所有患者的基础治疗。", 10.5),
    ]:
        page.insert_text((72, y), text, fontname="china-s", fontsize=size)
        y += size + 10
    doc.save(p)
    doc.close()
    return p


def _flatten(sections):
    for s in sections:
        yield s
        yield from _flatten(s.children)


def test_pdf_headings_by_font_size(tmp_path: Path):
    doc = PdfParser().parse(
        _make_pdf(tmp_path), department="心血管", source_path="data/raw/pdf/demo.pdf"
    )
    titles = [(s.level, s.title) for s in _flatten(doc.sections)]
    assert (1, "中国高血压临床实践指南") in titles
    assert (2, "1 诊断标准") in titles
    assert (2, "2 治疗原则") in titles
    body = doc.sections[0].children[0].text
    assert "SBP≥140" in body


def test_pdf_doc_metadata(tmp_path: Path):
    doc = PdfParser().parse(
        _make_pdf(tmp_path), department="心血管", source_path="data/raw/pdf/demo.pdf"
    )
    assert doc.title == "中国高血压临床实践指南"
    assert doc.department == "心血管"
    assert doc.doc_type == "guideline"
    assert len(doc.doc_hash) == 16


def test_pdf_no_text_page(tmp_path: Path):
    p = tmp_path / "blank.pdf"
    d = fitz.open()
    d.new_page()
    d.save(p)
    d.close()
    doc = PdfParser().parse(p, department="综合", source_path="x.pdf")
    assert "扫描件" in doc.sections[0].text
