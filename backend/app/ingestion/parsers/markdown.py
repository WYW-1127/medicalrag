from pathlib import Path

from app.ingestion.models import ParsedDocument
from app.ingestion.registry import file_hash
from app.ingestion.tree import SectionTreeBuilder


class MarkdownParser:
    """行级扫描：# 标题定位层级，| 连续行聚合为表格节点，其余为正文。

    不依赖 markdown-it 的 token 流——行级处理对医学指南类文档更稳（标题/表格/段落简单直接）。
    """

    def parse(self, path: Path, *, department: str, source_path: str) -> ParsedDocument:
        text = path.read_text(encoding="utf-8")
        return self.parse_text(text, path=path, department=department, source_path=source_path)

    def parse_text(
        self, text: str, *, path: Path, department: str, source_path: str
    ) -> ParsedDocument:
        lines = text.splitlines()
        builder = SectionTreeBuilder()
        title = path.stem
        got_title = False
        table_buf: list[str] = []

        def flush_table() -> None:
            nonlocal table_buf
            if table_buf:
                builder.add_table("\n".join(table_buf), "表格")
                table_buf = []

        in_code = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                builder.add_text(line)
                continue
            heading = self._heading(stripped)
            if heading:
                flush_table()
                level, text_t = heading
                builder.add_heading(level, text_t)
                if not got_title and text_t:
                    title, got_title = text_t, True
                continue
            if stripped.startswith("|"):
                table_buf.append(stripped)
                continue
            flush_table()
            builder.add_text(line)
        flush_table()
        return ParsedDocument(
            source_path=source_path,
            doc_type="guideline",
            department=department,
            title=title,
            doc_hash=file_hash(path),
            sections=builder.build(),
        )

    @staticmethod
    def _heading(line: str) -> tuple[int, str] | None:
        n = len(line) - len(line.lstrip("#"))
        if 1 <= n <= 6 and line[n : n + 1] == " ":
            return n, line[n + 1 :].strip()
        return None
