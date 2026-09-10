import csv
import json
from pathlib import Path

from app.ingestion.models import ParsedDocument, Section
from app.ingestion.registry import file_hash
from app.ingestion.tree import SectionTreeBuilder

RECORDS_PER_SECTION = 20


class StructuredParser:
    """结构化数据：JSON 药品说明书（约定 {"name","department","fields"}）与通用 CSV。"""

    def parse(self, path: Path, *, department: str, source_path: str) -> ParsedDocument:
        if path.suffix.lower() == ".json":
            return self._parse_json(path, department, source_path)
        return self._parse_csv(path, department, source_path)

    def _parse_json(self, path: Path, department: str, source_path: str) -> ParsedDocument:
        data = json.loads(path.read_text(encoding="utf-8"))
        builder = SectionTreeBuilder()
        title = str(data.get("name", path.stem))
        builder.add_heading(1, title)
        for key, value in (data.get("fields") or {}).items():
            builder.add_heading(2, str(key))
            builder.add_text(str(value))
        return ParsedDocument(
            source_path=source_path,
            doc_type="drug_label",
            department=str(data.get("department", department)),
            title=title,
            doc_hash=file_hash(path),
            sections=builder.build(),
        )

    def _parse_csv(self, path: Path, department: str, source_path: str) -> ParsedDocument:
        builder = SectionTreeBuilder()
        builder.add_heading(1, path.stem)
        with path.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        if len(rows) <= 1:
            sections = [Section(level=1, title=path.stem, text="（空表）")]
            return ParsedDocument(
                source_path=source_path,
                doc_type="structured_table",
                department=department,
                title=path.stem,
                doc_hash=file_hash(path),
                sections=sections,
            )
        header = rows[0]
        for start in range(1, len(rows), RECORDS_PER_SECTION):
            batch = rows[start : start + RECORDS_PER_SECTION]
            builder.add_heading(2, f"记录 {start}-{start + len(batch) - 1}")
            for row in batch:
                builder.add_text(
                    "；".join(f"{h}：{v}" for h, v in zip(header, row, strict=False))
                )
        return ParsedDocument(
            source_path=source_path,
            doc_type="structured_table",
            department=department,
            title=path.stem,
            doc_hash=file_hash(path),
            sections=builder.build(),
        )
