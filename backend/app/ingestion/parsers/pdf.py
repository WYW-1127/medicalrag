from collections import Counter
from pathlib import Path
from typing import Any

import fitz

from app.ingestion.models import ParsedDocument
from app.ingestion.registry import file_hash
from app.ingestion.tree import SectionTreeBuilder


class _Line:
    __slots__ = ("text", "size", "x0", "x1", "y0")

    def __init__(self, text: str, size: float, x0: float, x1: float, y0: float) -> None:
        self.text, self.size, self.x0, self.x1, self.y0 = text, size, x0, x1, y0


class PdfParser:
    """启发式版面解析：字号聚类识别标题、宽度启发式识别双栏、find_tables 提取表格。

    局限（面试可讲的 trade-off）：不处理扫描件 OCR（检测到无文本层会显式标注）、
    标题识别依赖字号差异（对排版统一的 PDF 可能漏检，可退化为单节全文）。
    """

    def parse(self, path: Path, *, department: str, source_path: str) -> ParsedDocument:
        builder = SectionTreeBuilder()
        title = path.stem
        with fitz.open(path) as doc:
            for page in doc:
                self._parse_page(page, builder)
        sections = builder.build()
        first = sections[0] if sections else None
        if first and first.title and first.title != "__root__":
            title = first.title
        return ParsedDocument(
            source_path=source_path,
            doc_type="guideline",
            department=department,
            title=title,
            doc_hash=file_hash(path),
            sections=sections,
        )

    # ---- 页级处理 ----
    def _parse_page(self, page: fitz.Page, builder: SectionTreeBuilder) -> None:
        page_no = page.number + 1
        tables = self._extract_tables(page)
        lines = self._page_lines(page, skip_bboxes=[t["bbox"] for t in tables])
        if not lines and not tables:
            builder.add_text(f"（第 {page_no} 页无可提取文本，疑似扫描件）")
            return
        body_size = self._body_size(lines)
        heading_sizes = self._heading_sizes(lines, body_size)
        two_col = self._is_two_column(lines, page.rect.width)
        lines.sort(key=lambda ln: self._order_key(ln, two_col, page.rect.width))
        for line in lines:
            size_rank = heading_sizes.get(round(line.size, 1))
            if size_rank and len(line.text.strip()) <= 60:
                builder.add_heading(size_rank, line.text.strip())
            else:
                builder.add_text(line.text)
        for t in tables:
            builder.add_table(t["markdown"], f"表格(P{page_no})", page_no)

    def _page_lines(
        self, page: fitz.Page, skip_bboxes: list[tuple[float, float, float, float]]
    ) -> list[_Line]:
        out: list[_Line] = []
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                spans: list[dict[str, Any]] = line["spans"]
                if not spans:
                    continue
                x0 = min(s["bbox"][0] for s in spans)
                x1 = max(s["bbox"][2] for s in spans)
                y0 = line["bbox"][1]
                cx, cy = (x0 + x1) / 2, y0
                if any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in skip_bboxes):
                    continue
                text = "".join(s["text"] for s in spans).strip()
                if not text:
                    continue
                size = max(s["size"] for s in spans)
                out.append(_Line(text, size, x0, x1, y0))
        return out

    def _extract_tables(self, page: fitz.Page) -> list[dict[str, Any]]:
        tables: list[dict[str, Any]] = []
        try:
            found = page.find_tables()
        except Exception:
            return tables
        for t in found.tables:
            try:
                md = t.to_markdown()
            except Exception:
                rows = t.extract()
                md = "\n".join(
                    " | ".join("" if c is None else str(c) for c in row) for row in rows
                )
            if len(md.replace("\n", " ").strip()) < 8:  # 噪声表格跳过
                continue
            bbox = t.bbox
            tables.append({"bbox": (bbox[0], bbox[1], bbox[2], bbox[3]), "markdown": md})
        return tables

    @staticmethod
    def _body_size(lines: list[_Line]) -> float:
        if not lines:
            return 10.0
        weighted: Counter[float] = Counter()
        for ln in lines:
            weighted[round(ln.size, 1)] += len(ln.text)
        return weighted.most_common(1)[0][0]

    @staticmethod
    def _heading_sizes(lines: list[_Line], body: float) -> dict[float, int]:
        sizes = {round(ln.size, 1) for ln in lines if ln.size >= body * 1.15}
        ranked = sorted(sizes, reverse=True)[:3]
        return {s: i + 1 for i, s in enumerate(ranked)}

    @staticmethod
    def _is_two_column(lines: list[_Line], page_width: float) -> bool:
        if not lines:
            return False
        widths = sorted(ln.x1 - ln.x0 for ln in lines)
        median_w = widths[len(widths) // 2]
        return median_w < page_width * 0.62

    @staticmethod
    def _order_key(ln: _Line, two_col: bool, page_width: float) -> tuple[int, float]:
        if two_col:
            col = 0 if (ln.x0 + ln.x1) / 2 < page_width / 2 else 1
            return (col, round(ln.y0, 1))
        return (0, round(ln.y0 * 10 + ln.x0 / 100, 2))
