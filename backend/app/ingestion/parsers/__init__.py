from pathlib import Path
from typing import Protocol

from app.ingestion.models import ParsedDocument


class Parser(Protocol):
    def parse(self, path: Path, *, department: str, source_path: str) -> ParsedDocument: ...


def get_parser(path: Path) -> Parser:
    """按后缀分发到对应解析器；未支持的后缀抛 ValueError。"""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from app.ingestion.parsers.pdf import PdfParser

        return PdfParser()
    if suffix in {".md", ".markdown"}:
        from app.ingestion.parsers.markdown import MarkdownParser

        return MarkdownParser()
    if suffix in {".html", ".htm"}:
        from app.ingestion.parsers.html import HtmlParser

        return HtmlParser()
    if suffix == ".docx":
        from app.ingestion.parsers.docx import DocxParser

        return DocxParser()
    if suffix in {".json", ".csv"}:
        from app.ingestion.parsers.structured import StructuredParser

        return StructuredParser()
    raise ValueError(f"不支持的文件格式: {path.suffix}（{path.name}）")
