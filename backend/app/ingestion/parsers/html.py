import re
from pathlib import Path

import trafilatura

from app.ingestion.models import ParsedDocument
from app.ingestion.parsers.markdown import MarkdownParser

_TAG_RE = re.compile(r"<[^>]+>")
_HEADING_RE = re.compile(r"<h([1-6])[^>]*>(.*?)</h\1>", re.S | re.I)


def _heading_levels(html: str) -> dict[str, int]:
    """原始 HTML 的 h1-h6 文本 → 层级（去重，首个优先）。"""
    out: dict[str, int] = {}
    for level, inner in _HEADING_RE.findall(html):
        text = re.sub(r"\s+", " ", _TAG_RE.sub("", inner)).strip()
        if text and text not in out:
            out[text] = int(level)
    return out


def _mark_headings(md_text: str, headings: dict[str, int]) -> str:
    """trafilatura 的 markdown 输出不带 # 前缀；按原文标题集合补回层级标记。"""
    lines = []
    for line in md_text.splitlines():
        key = re.sub(r"\s+", " ", line).strip()
        level = headings.get(key)
        lines.append(f"{'#' * level} {line.strip()}" if level else line)
    return "\n".join(lines)


class HtmlParser:
    """trafilatura 正文抽取 + 原文 h 标签回标 → 复用 Markdown 解析的行级逻辑。"""

    def __init__(self) -> None:
        self._md = MarkdownParser()

    def parse(self, path: Path, *, department: str, source_path: str) -> ParsedDocument:
        html = path.read_text(encoding="utf-8", errors="ignore")
        extracted = trafilatura.extract(
            html, output_format="markdown", include_tables=True, no_fallback=False
        )
        if not extracted:
            extracted = path.stem  # 抽取失败退化为单节文档
        marked = _mark_headings(extracted, _heading_levels(html))
        return self._md.parse_text(
            marked, path=path, department=department, source_path=source_path
        )
