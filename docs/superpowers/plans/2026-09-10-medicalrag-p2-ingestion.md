# MedicalRAG P2 数据与 Ingestion 管线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `data/raw/` → 多格式解析 → 统一文档树 → 结构感知分块 → BGE-M3 向量化 → Milvus 混合索引（dense + BM25 sparse + 元数据）的幂等离线入库管线，含 `python -m app.ingestion` CLI 与端到端冒烟验证。

**Architecture:** 纯函数式解析器（每种格式一个类，输出统一的 Pydantic 文档 IR `ParsedDocument → Section 树`）+ 三种可配置分块策略（structural/fixed/recursive，供 P7 消融）+ `MilvusStore`（BM25 函数自动由 text 生成 sparse 向量，中文 jieba analyzer，按 doc_hash 删除-重插实现幂等）+ CLI 编排。解析与分块全部可单测（CI 无 Milvus 也能跑），Milvus 写入通过真实实例在冒烟步骤验证。

**Tech Stack:** 新增依赖 pymupdf（PDF）、markdown-it-py（MD 标题树）、trafilatura（HTML 正文）、python-docx（DOCX）；复用 P1 的 EmbeddingProvider、Settings、Milvus（docker 容器已在跑）。

**Spec:** `docs/superpowers/specs/2026-09-10-medicalrag-design.md` §3（数据与 Ingestion 管线）

## Global Constraints

- 沿用 P1 全部门禁：`pytest` 全绿 + `ruff check .` 0 错 + `mypy app` 0 错；Conventional Commits
- CI（GitHub Actions）不启动 Milvus/MySQL —— Milvus 相关类用 client 注入 + mock 单测；真实写入只在本机冒烟步骤验证
- 解析器/分块器是纯函数式（输入路径/文档，输出 IR/chunk），不做网络与 DB 操作
- 密钥零硬编码；`.env` 已有 Embedding key 可用（已验证 `[ok] embed`）
- Milvus collection：`medical_chunks`，dim=1024，BM25(jieba) + HNSW(COSINE)
- 目录约定：`data/raw/{pdf,markdown,html,docx,structured}` 按格式分目录；科室为格式目录下的**子目录名**（如 `data/raw/pdf/心血管/xxx.pdf`），无子目录默认 `综合`；doc_type 约定：`.json→drug_label`、`.csv→structured_table`、其余→`guideline`

---

### Task 1: 文档 IR 模型、分块配置与解析器注册表

**Files:**
- Modify: `backend/pyproject.toml`（加依赖）
- Create: `backend/app/ingestion/__init__.py`
- Create: `backend/app/ingestion/models.py`（IR：Section/ParsedDocument/Chunk）
- Create: `backend/app/ingestion/registry.py`（格式→解析器注册表 + doc_hash 工具）
- Modify: `backend/app/core/config.py`（加 ChunkingSettings + milvus_collection）
- Test: `backend/tests/test_ingestion_models.py`

**Interfaces:**
- Produces:
  - `Section(BaseModel)`：`level: int`、`title: str`、`text: str = ""`、`page: int | None = None`、`is_table: bool = False`、`children: list[Section] = []`
  - `ParsedDocument(BaseModel)`：`source_path: str`（相对仓库根）、`doc_type: str`、`department: str`、`title: str`、`doc_hash: str`、`sections: list[Section]`
  - `Chunk(BaseModel)`：`chunk_id: str`、`doc_hash: str`、`text: str`、`section_path: str`、`page: int | None`、`seq: int`
  - `file_hash(path: Path) -> str`（sha256 hex 前 16 位）；`department_for(path: Path, data_root: Path) -> str`
  - `doc_type_for(suffix: str) -> str`
  - `Settings.chunking: ChunkingSettings`（`strategy="structural"`, `max_chars=600`, `min_chars=100`, `overlap=80`, `table_max_chars=4000`）；`Settings.milvus_collection: str = "medical_chunks"`

- [ ] **Step 1: pyproject.toml dependencies 增加**

```toml
    "pymupdf>=1.24",
    "markdown-it-py>=3.0",
    "trafilatura>=1.12",
    "python-docx>=1.1",
```

- [ ] **Step 2: 写 `backend/app/ingestion/models.py`**

```python
from pydantic import BaseModel, Field


class Section(BaseModel):
    """文档树的节点：一个标题及其直接正文；表格节点 title 形如「表格(P3#1)」。"""

    level: int
    title: str
    text: str = ""
    page: int | None = None
    is_table: bool = False
    children: list["Section"] = Field(default_factory=list)


class ParsedDocument(BaseModel):
    """所有格式解析器的统一输出（中间表示）。"""

    source_path: str
    doc_type: str
    department: str
    title: str
    doc_hash: str
    sections: list[Section]


class Chunk(BaseModel):
    """入库检索单元。chunk_id 确定性生成（doc_hash+seq），支持幂等重插。"""

    chunk_id: str
    doc_hash: str
    text: str
    section_path: str
    page: int | None
    seq: int
```

- [ ] **Step 3: 写 `backend/app/ingestion/registry.py`**

```python
import hashlib
from pathlib import Path

_DOC_TYPES = {".json": "drug_label", ".csv": "structured_table"}


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()[:16]


def doc_type_for(suffix: str) -> str:
    return _DOC_TYPES.get(suffix.lower(), "guideline")


def department_for(path: Path, data_root: Path) -> str:
    """科室 = 格式目录（pdf/markdown/...）下的子目录名；无子目录则为「综合」。"""
    rel = path.relative_to(data_root).parts
    if len(rel) >= 3:  # {format}/{department}/{file}
        return rel[-2]
    return "综合"
```

- [ ] **Step 4: config.py 增加 ChunkingSettings 与 milvus_collection**

```python
class ChunkingSettings(BaseModel):
    strategy: str = "structural"  # structural | fixed | recursive（P7 消融用）
    max_chars: int = 600
    min_chars: int = 100
    overlap: int = 80
    table_max_chars: int = 4000
```

`Settings` 增加字段：`milvus_collection: str = "medical_chunks"`、`chunking: ChunkingSettings = ChunkingSettings()`。

- [ ] **Step 5: 测试 `backend/tests/test_ingestion_models.py`**

```python
from pathlib import Path

from app.ingestion.registry import department_for, doc_type_for, file_hash
from app.ingestion.models import Chunk, ParsedDocument, Section


def test_doc_type_by_suffix():
    assert doc_type_for(".json") == "drug_label"
    assert doc_type_for(".CSV") == "structured_table"
    assert doc_type_for(".pdf") == "guideline"


def test_department_from_subdir(tmp_path: Path):
    (tmp_path / "pdf" / "心血管").mkdir(parents=True)
    f = tmp_path / "pdf" / "心血管" / "指南.pdf"
    f.touch()
    assert department_for(f, tmp_path) == "心血管"
    assert department_for(tmp_path / "pdf" / "顶层.pdf", tmp_path) == "综合"


def test_file_hash_stable(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("医学", encoding="utf-8")
    assert file_hash(f) == file_hash(f)
    assert len(file_hash(f)) == 16


def test_section_tree_roundtrip():
    root = Section(level=1, title="指南", children=[Section(level=2, title="诊断", text="内容")])
    doc = ParsedDocument(
        source_path="x.md", doc_type="guideline", department="综合",
        title="指南", doc_hash="ab" * 8, sections=[root],
    )
    c = Chunk(chunk_id="abc-0001", doc_hash="ab" * 8, text="内容",
              section_path="指南 > 诊断", page=None, seq=1)
    assert doc.sections[0].children[0].text == c.text
```

- [ ] **Step 6: `uv sync` → pytest/ruff/mypy 全绿 → Commit** `feat: 文档 IR 模型与解析器注册表`

---

### Task 2: Markdown 解析器（标题树核心）

**Files:**
- Create: `backend/app/ingestion/tree.py`（SectionTreeBuilder，供 MD/PDF/DOCX 复用）
- Create: `backend/app/ingestion/parsers/markdown.py`
- Create: `backend/app/ingestion/parsers/__init__.py`
- Test: `backend/tests/test_parser_markdown.py`

**Interfaces:**
- Produces:
  - `SectionTreeBuilder.add_heading(level: int, title: str) -> None`；`add_text(line: str) -> None`（追加到当前最深节点）；`add_table(md_text: str, title: str, page: int | None = None) -> None`；`build() -> list[Section]`
  - `MarkdownParser.parse(path: Path, *, department: str, source_path: str) -> ParsedDocument`（标题层级 h1-h6 → level 1-6；标题前正文挂到虚拟根 level=0 不输出）

- [ ] **Step 1: 写 `backend/app/ingestion/tree.py`**

```python
from app.ingestion.models import Section


class SectionTreeBuilder:
    """栈式构建标题层级树；MD/PDF/DOCX 解析共用。"""

    def __init__(self) -> None:
        self._root = Section(level=0, title="__root__")
        self._stack: list[Section] = [self._root]

    def _current(self) -> Section:
        return self._stack[-1]

    def add_heading(self, level: int, title: str) -> None:
        while self._stack[-1].level >= level:
            self._stack.pop()
        node = Section(level=level, title=title)
        self._stack[-1].children.append(node)
        self._stack.append(node)

    def add_text(self, line: str) -> None:
        if not line.strip():
            return
        cur = self._current()
        cur.text = f"{cur.text}\n{line.strip()}".strip()

    def add_table(self, md_text: str, title: str, page: int | None = None) -> None:
        self._stack[-1].children.append(
            Section(level=self._stack[-1].level + 1, title=title, text=md_text.strip(),
                    page=page, is_table=True)
        )

    def build(self) -> list[Section]:
        return self._root.children if self._root.children else [self._root]
```

- [ ] **Step 2: 写 `backend/app/ingestion/parsers/markdown.py`**

```python
from pathlib import Path

from markdown_it import MarkdownIt

from app.ingestion.models import ParsedDocument
from app.ingestion.registry import file_hash
from app.ingestion.tree import SectionTreeBuilder


class MarkdownParser:
    """markdown-it-py token 流 → Section 树。表格块（| 开头的行组）转 is_table 节点。"""

    _md = MarkdownIt("commonmark").enable("table")

    def parse(self, path: Path, *, department: str, source_path: str) -> ParsedDocument:
        raw = path.read_text(encoding="utf-8")
        builder = SectionTreeBuilder()
        title = path.stem
        table_buf: list[str] = []

        def flush_table() -> None:
            if table_buf:
                builder.add_table("\n".join(table_buf), "表格")
                table_buf.clear()

        for token in self._md.parse(raw):
            if token.type == "heading_open":
                flush_table()
                builder.add_heading(int(token.tag[1]), "")
            elif token.type == "inline":
                # inline 属于当前 heading 或段落；由外层 token 决定归属
                if builder._stack[-1].level > 0 and not builder._stack[-1].title:  # noqa: SLF001
                    builder._stack[-1].title = token.content.strip()  # noqa: SLF001
                    if not title or title == path.stem:
                        pass
                else:
                    _feed_inline(builder, token.content, table_buf)
            elif token.type == "table_open":
                flush_table()
            elif token.type in ("th_open", "td_open"):
                pass
        flush_table()
        ...  # 见 Step 3 完整版
```

> 注：上面是骨架示意；**实现时采用更稳的行级处理**（不逐 token）：用 `MarkdownIt` 只定位 heading 结构，正文按行扫描（`|` 连续行 → 表格缓冲，否则正文），完整逻辑以 Step 3 为准。

- [ ] **Step 3: 实际实现（行级扫描版，写入 markdown.py 最终版）**

```python
from pathlib import Path

from markdown_it import MarkdownIt

from app.ingestion.models import ParsedDocument
from app.ingestion.registry import file_hash
from app.ingestion.tree import SectionTreeBuilder

_HEADING_RE_CACHE: dict[str, int] = {}


class MarkdownParser:
    """heading 用 markdown-it 定位；正文/表格行级扫描。"""

    _md = MarkdownIt("commonmark")

    def parse(self, path: Path, *, department: str, source_path: str) -> ParsedDocument:
        lines = path.read_text(encoding="utf-8").splitlines()
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
            if line.strip().startswith("```"):
                in_code = not in_code
                builder.add_text(line)
                continue
            if in_code:
                builder.add_text(line)
                continue
            m = self._heading(line)
            if m:
                flush_table()
                level, text = m
                builder.add_heading(level, text)
                if not got_title:
                    title, got_title = text, True
                continue
            if line.lstrip().startswith("|"):
                table_buf.append(line.strip())
                continue
            flush_table()
            builder.add_text(line)
        flush_table()
        return ParsedDocument(
            source_path=source_path, doc_type="guideline", department=department,
            title=title, doc_hash=file_hash(path), sections=builder.build(),
        )

    @staticmethod
    def _heading(line: str) -> tuple[int, str] | None:
        s = line.lstrip()
        n = len(s) - len(s.lstrip("#"))
        if 1 <= n <= 6 and s[n : n + 1] == " ":
            return n, s[n + 1 :].strip()
        return None
```

（`_HEADING_RE_CACHE` 删除，不需要。）

- [ ] **Step 4: 测试 `backend/tests/test_parser_markdown.py`**

```python
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
    return MarkdownParser().parse(f, department="心血管", source_path="data/samples/guide.md")


def test_heading_tree_structure(tmp_path: Path):
    doc = _parse(tmp_path)
    top = [s.title for s in doc.sections]
    assert top == ["高血压防治指南", "附录"]
    ch1 = doc.sections[0].children
    assert [c.title for c in ch1] == ["1. 诊断标准", "2. 分级"]
    assert ch1[0].text.startswith("诊室血压")
    assert ch1[1].children[0].title == "2.1 说明"


def test_table_kept_as_table_node(tmp_path: Path):
    doc = _parse(tmp_path)
    tables = [s for s in doc.sections[0].children if s.is_table]
    assert len(tables) == 1
    assert "140-159" in tables[0].text
    assert tables[0].text.startswith("|")


def test_doc_metadata(tmp_path: Path):
    doc = _parse(tmp_path)
    assert doc.title == "高血压防治指南"
    assert doc.department == "心血管"
    assert doc.doc_type == "guideline"
    assert len(doc.doc_hash) == 16
```

- [ ] **Step 5: pytest/ruff/mypy 全绿 → Commit** `feat: Markdown 解析器与 Section 树构建器`

---

### Task 3: PDF 解析器（字号聚类标题 + 多栏 + 表格）

**Files:**
- Create: `backend/app/ingestion/parsers/pdf.py`
- Test: `backend/tests/test_parser_pdf.py`（fixture PDF 由 PyMuPDF 动态生成，不入 git）

**Interfaces:**
- Produces: `PdfParser.parse(path: Path, *, department: str, source_path: str) -> ParsedDocument`
  - 标题识别：行主字号显著大于正文字号（≥1.15 倍）且行长 ≤ 60 字 → 标题；按字号降序分桶映射 level 1-3
  - 多栏：行宽中位数 < 页宽 0.62 → 双栏阅读序（先左栏后右栏，栏内按 y）
  - 表格：`page.find_tables()` → markdown（`to_markdown()`，失败时手工拼接），表格 bbox 内的行从正文剔除，表格作为 `is_table` 节点
- 实现注记：`page.get_text("dict")` 取行/spans；空 PDF/扫描件（无文本层）返回单节 `"（无可提取文本，疑似扫描件）"`

- [ ] **Step 1: 写 `backend/app/ingestion/parsers/pdf.py`**

```python
from collections import Counter
from pathlib import Path

import fitz

from app.ingestion.models import ParsedDocument, Section
from app.ingestion.registry import file_hash
from app.ingestion.tree import SectionTreeBuilder


class _Line:
    __slots__ = ("text", "size", "x0", "x1", "y0")

    def __init__(self, text: str, size: float, x0: float, x1: float, y0: float) -> None:
        self.text, self.size, self.x0, self.x1, self.y0 = text, size, x0, x1, y0


class PdfParser:
    """启发式版面解析：字号聚类识别标题、宽度启发式识别双栏、find_tables 提取表格。"""

    def parse(self, path: Path, *, department: str, source_path: str) -> ParsedDocument:
        builder = SectionTreeBuilder()
        title = path.stem
        with fitz.open(path) as doc:
            for page in doc:
                self._parse_page(page, builder)
        sections = builder.build()
        if sections and sections[0].level <= 3 and sections[0].title:
            title = sections[0].title
        return ParsedDocument(
            source_path=source_path, doc_type="guideline", department=department,
            title=title, doc_hash=file_hash(path), sections=sections,
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

    def _page_lines(self, page: fitz.Page, skip_bboxes: list[tuple[float, float, float, float]]) -> list[_Line]:
        out: list[_Line] = []
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                spans = line["spans"]
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

    def _extract_tables(self, page: fitz.Page) -> list[dict]:
        tables = []
        try:
            found = page.find_tables()
        except Exception:
            found = None
        if not found:
            return tables
        for t in found.tables:
            try:
                md = t.to_markdown()
            except Exception:
                rows = t.extract()
                md = "\n".join(" | ".join("" if c is None else str(c) for c in row) for row in rows)
            clean = md.replace("\n", " ").strip()
            if len(clean) < 8:  # 噪声表格跳过
                continue
            tables.append({"bbox": tuple(t.bbox), "markdown": md})
        return tables

    @staticmethod
    def _body_size(lines: list[_Line]) -> float:
        if not lines:
            return 10.0
        weighted = Counter()
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
```

- [ ] **Step 2: 测试（fixture PDF 动态生成）`backend/tests/test_parser_pdf.py`**

```python
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
        ("诊室血压 SBP≥140mmHg 和/或 DBP≥90mmHg 可诊断高血压。", 10.5),
        ("在未使用降压药的情况下，非同日三次测量均达到上述标准。", 10.5),
        ("2 治疗原则", 14),
        ("生活方式干预是所有患者的基础治疗。", 10.5),
    ]:
        page.insert_text((72, y), text, fontname="china-s", fontsize=size)
        y += size + 10
    doc.save(p)
    doc.close()
    return p


def test_pdf_headings_by_font_size(tmp_path: Path):
    doc = PdfParser().parse(_make_pdf(tmp_path), department="心血管",
                            source_path="data/raw/pdf/demo.pdf")
    titles = [(s.level, s.title) for s in doc.sections]
    assert (1, "中国高血压临床实践指南") in titles
    assert (2, "1 诊断标准") in titles
    assert (2, "2 治疗原则") in titles
    body = doc.sections[0].children[0].text
    assert "SBP≥140" in body


def test_pdf_doc_metadata(tmp_path: Path):
    doc = PdfParser().parse(_make_pdf(tmp_path), department="心血管",
                            source_path="data/raw/pdf/demo.pdf")
    assert doc.title == "中国高血压临床实践指南"
    assert doc.department == "心血管"
    assert len(doc.doc_hash) == 16


def test_pdf_no_text_page(tmp_path: Path):
    p = tmp_path / "blank.pdf"
    d = fitz.open()
    d.new_page()
    d.save(p)
    d.close()
    doc = PdfParser().parse(p, department="综合", source_path="x.pdf")
    assert "扫描件" in doc.sections[0].text
```

（注意：`insert_text` 用 `china-s` 内置中文字体；若该字体不可用导致文本提取为空，改用 `page.insert_textbox` + `fontname="helv"` 英文 fixture——执行时以实际可提取为准，断言同步调整文案。）

- [ ] **Step 3: pytest/ruff/mypy 全绿 → Commit** `feat: PDF 启发式解析器（字号标题/双栏/表格）`

---

### Task 4: HTML / DOCX / JSON / CSV 解析器

**Files:**
- Create: `backend/app/ingestion/parsers/html.py`
- Create: `backend/app/ingestion/parsers/docx.py`
- Create: `backend/app/ingestion/parsers/structured.py`
- Modify: `backend/app/ingestion/parsers/__init__.py`（`get_parser(path) -> 解析器实例`，未支持后缀抛 `ValueError`）
- Test: `backend/tests/test_parser_others.py`

**Interfaces:**
- Produces:
  - `HtmlParser.parse(...)`：trafilatura `extract(output_format="markdown")` → 复用 MarkdownParser 行级逻辑；提取失败回退纯文本单节
  - `DocxParser.parse(...)`：`python-docx` 段落，style 名 `Heading N` → level N；docx 内嵌表格逐个转 markdown（` | ` 拼接）作为 is_table 节点
  - `StructuredParser.parse(...)`：
    - `.json`：约定 `{"name": str, "department": str, "fields": {字段名: 内容}}` → 每字段一个 level=2 Section
    - `.csv`：首行为表头；每行转「列名: 值；...」文本，每 20 行聚合成一个 level=2 Section（title=「记录 1-20」）
  - `get_parser(path: Path)`：按后缀分发（.pdf/.md/.html/.htm/.docx/.json/.csv）

- [ ] **Step 1: 实现 html.py / docx.py / structured.py（接口签名与 MarkdownParser 一致）**

html.py：

```python
from pathlib import Path

import trafilatura

from app.ingestion.models import ParsedDocument
from app.ingestion.parsers.markdown import MarkdownParser
from app.ingestion.registry import file_hash
from app.ingestion.tree import SectionTreeBuilder


class HtmlParser:
    """trafilatura 正文抽取（markdown 输出）→ 复用 Markdown 解析的行级逻辑。"""

    def __init__(self) -> None:
        self._md = MarkdownParser()

    def parse(self, path: Path, *, department: str, source_path: str) -> ParsedDocument:
        html = path.read_text(encoding="utf-8", errors="ignore")
        extracted = trafilatura.extract(html, output_format="markdown",
                                        include_tables=True, no_fallback=False)
        doc = self._md.parse_text(extracted or path.stem, path=path, department=department,
                                  source_path=source_path)
        return doc
```

（实现时给 `MarkdownParser` 增加 `parse_text(text, *, path, department, source_path)` 方法，`parse()` 调用它——避免临时文件。）

docx.py：

```python
from pathlib import Path

from docx import Document

from app.ingestion.models import ParsedDocument
from app.ingestion.registry import file_hash
from app.ingestion.tree import SectionTreeBuilder


class DocxParser:
    def parse(self, path: Path, *, department: str, source_path: str) -> ParsedDocument:
        builder = SectionTreeBuilder()
        d = Document(str(path))
        for p in d.paragraphs:
            style = (p.style.name or "").lower()
            if style.startswith("heading"):
                try:
                    level = int(style.split()[-1])
                except ValueError:
                    level = 2
                if p.text.strip():
                    builder.add_heading(level, p.text.strip())
            elif p.text.strip():
                builder.add_text(p.text)
        for i, tbl in enumerate(d.tables, 1):
            rows = [" | ".join(c.text.strip() for c in r.cells) for r in tbl.rows]
            builder.add_table("\n".join(rows), f"表格(#{i})")
        return ParsedDocument(
            source_path=source_path, doc_type="guideline", department=department,
            title=path.stem, doc_hash=file_hash(path), sections=builder.build(),
        )
```

structured.py：

```python
import csv
import json
from pathlib import Path

from app.ingestion.models import ParsedDocument, Section
from app.ingestion.registry import file_hash
from app.ingestion.tree import SectionTreeBuilder

RECORDS_PER_SECTION = 20


class StructuredParser:
    def parse(self, path: Path, *, department: str, source_path: str) -> ParsedDocument:
        if path.suffix.lower() == ".json":
            return self._parse_json(path, department, source_path)
        return self._parse_csv(path, department, source_path)

    def _parse_json(self, path: Path, department: str, source_path: str) -> ParsedDocument:
        data = json.loads(path.read_text(encoding="utf-8"))
        builder = SectionTreeBuilder()
        builder.add_heading(1, str(data.get("name", path.stem)))
        for key, value in (data.get("fields") or {}).items():
            builder.add_heading(2, str(key))
            builder.add_text(str(value))
        return ParsedDocument(
            source_path=source_path, doc_type="drug_label",
            department=str(data.get("department", department)),
            title=str(data.get("name", path.stem)), doc_hash=file_hash(path),
            sections=builder.build(),
        )

    def _parse_csv(self, path: Path, department: str, source_path: str) -> ParsedDocument:
        builder = SectionTreeBuilder()
        builder.add_heading(1, path.stem)
        with path.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        if not rows:
            sections = [Section(level=1, title=path.stem, text="（空表）")]
            return ParsedDocument(source_path=source_path, doc_type="structured_table",
                                  department=department, title=path.stem,
                                  doc_hash=file_hash(path), sections=sections)
        header = rows[0]
        for start in range(1, len(rows), RECORDS_PER_SECTION):
            batch = rows[start : start + RECORDS_PER_SECTION]
            builder.add_heading(2, f"记录 {start}-{start + len(batch) - 1}")
            for row in batch:
                builder.add_text("；".join(f"{h}：{v}" for h, v in zip(header, row, strict=False)))
        return ParsedDocument(
            source_path=source_path, doc_type="structured_table", department=department,
            title=path.stem, doc_hash=file_hash(path), sections=builder.build(),
        )
```

parsers/__init__.py：

```python
from pathlib import Path

from app.ingestion.parsers.docx import DocxParser
from app.ingestion.parsers.html import HtmlParser
from app.ingestion.parsers.markdown import MarkdownParser
from app.ingestion.parsers.pdf import PdfParser
from app.ingestion.parsers.structured import StructuredParser

_PARSERS = {
    ".pdf": PdfParser, ".md": MarkdownParser,
    ".html": HtmlParser, ".htm": HtmlParser,
    ".docx": DocxParser, ".json": StructuredParser, ".csv": StructuredParser,
}


def get_parser(path: Path):
    cls = _PARSERS.get(path.suffix.lower())
    if cls is None:
        raise ValueError(f"不支持的文件格式: {path.suffix}（{path.name}）")
    return cls()
```

- [ ] **Step 2: 测试 `backend/tests/test_parser_others.py`**

```python
import json
from pathlib import Path

from docx import Document

from app.ingestion.parsers import get_parser
from app.ingestion.parsers.docx import DocxParser
from app.ingestion.parsers.html import HtmlParser
from app.ingestion.parsers.structured import StructuredParser


def test_html_parser_extracts_markdown(tmp_path: Path):
    html = """<html><body><article>
    <h1>冠心病诊疗指南</h1><p>冠心病的主要危险因素包括高血压与糖尿病。</p>
    <h2>诊断</h2><p>依据典型心绞痛症状与心电图改变。</p>
    </article></body></html>"""
    f = tmp_path / "g.html"
    f.write_text(html, encoding="utf-8")
    doc = HtmlParser().parse(f, department="心血管", source_path="x.html")
    assert doc.title == "冠心病诊疗指南"
    assert any("高血压" in s.text for s in doc.sections[0].children)


def test_docx_parser_heading_and_table(tmp_path: Path):
    d = Document()
    d.add_heading("糖尿病指南", 1)
    d.add_heading("血糖控制目标", 2)
    d.add_paragraph("空腹血糖 4.4-7.0 mmol/L。")
    tbl = d.add_table(rows=2, cols=2)
    tbl.cell(0, 0).text = "指标"
    tbl.cell(0, 1).text = "目标"
    tbl.cell(1, 0).text = "HbA1c"
    tbl.cell(1, 1).text = "<7%"
    f = tmp_path / "d.docx"
    d.save(str(f))
    doc = DocxParser().parse(f, department="内分泌", source_path="d.docx")
    assert doc.sections[0].title == "糖尿病指南"
    assert any(s.is_table and "HbA1c" in s.text for s in doc.sections[0].children)


def test_json_drug_label(tmp_path: Path):
    data = {"name": "阿司匹林肠溶片", "department": "心血管",
            "fields": {"适应证": "心肌梗死、心绞痛", "禁忌": "活动性消化道出血"}}
    f = tmp_path / "asp.json"
    f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    doc = StructuredParser().parse(f, department="综合", source_path="a.json")
    assert doc.doc_type == "drug_label"
    assert doc.title == "阿司匹林肠溶片"
    fields = {c.title: c.text for c in doc.sections[0].children}
    assert fields["禁忌"] == "活动性消化道出血"


def test_csv_records_grouped(tmp_path: Path):
    f = tmp_path / "icd.csv"
    f.write_text("编码,名称\nI10,原发性高血压\nE11,2型糖尿病\n", encoding="utf-8-sig")
    doc = StructuredParser().parse(f, department="综合", source_path="i.csv")
    assert doc.doc_type == "structured_table"
    assert "I10" in doc.sections[0].children[0].text


def test_get_parser_dispatch(tmp_path: Path):
    assert get_parser(tmp_path / "a.md").__class__.__name__ == "MarkdownParser"
    assert get_parser(tmp_path / "a.pdf").__class__.__name__ == "PdfParser"
    try:
        get_parser(tmp_path / "a.txt")
        raise AssertionError("should raise")
    except ValueError:
        pass
```

- [ ] **Step 3: pytest/ruff/mypy 全绿 → Commit** `feat: HTML/DOCX/JSON/CSV 解析器与格式分发`

---

### Task 5: 分块器（structural / fixed / recursive）

**Files:**
- Create: `backend/app/ingestion/chunking.py`
- Test: `backend/tests/test_chunking.py`

**Interfaces:**
- Consumes: `ParsedDocument`/`Section`/`Chunk`（T1）、`ChunkingSettings`
- Produces: `chunk_document(doc: ParsedDocument, settings: ChunkingSettings) -> list[Chunk]`（内部按 `settings.strategy` 分发）
  - structural：DFS 遍历 Section 树，`section_path = " > ".join(各级标题)`；正文按句（`。；\n`）聚合到 `max_chars`，尾部 `overlap` 字符与下块重叠；`is_table` 节点整块保留（超 `table_max_chars` 按行组切并重复表头行）；小于 `min_chars` 的尾块并入前块
  - fixed：全文拼接（含标题行）按 `max_chars` 窗口 + `overlap` 滑窗（消融基线）
  - recursive：按 `["\n\n", "\n", "。", "；", "，"]` 递归切分聚合（消融基线）
  - `chunk_id = f"{doc_hash[:12]}-{seq:04d}"`，seq 从 0 递增

- [ ] **Step 1: 实现 `backend/app/ingestion/chunking.py`**

```python
from collections.abc import Iterator

from app.core.config import ChunkingSettings
from app.ingestion.models import Chunk, ParsedDocument, Section

_SENTENCE_BREAKS = "。；！？\n"


def chunk_document(doc: ParsedDocument, settings: ChunkingSettings) -> list[Chunk]:
    if settings.strategy == "structural":
        texts = _structural_pieces(doc)
    elif settings.strategy == "fixed":
        texts = _fixed_pieces(doc)
    elif settings.strategy == "recursive":
        texts = _recursive_pieces(doc)
    else:
        raise ValueError(f"未知分块策略: {settings.strategy}")
    return _assemble(doc, texts, settings)


# ---------- structural ----------
def _iter_sections(nodes: list[Section], path: list[str]) -> Iterator[tuple[Section, str]]:
    for node in nodes:
        cur = [*path, node.title]
        if node.is_table:
            yield node, " > ".join(cur)
        else:
            if node.text.strip():
                yield node, " > ".join(cur)
            yield from _iter_sections(node.children, cur)


def _structural_pieces(doc: ParsedDocument) -> list[tuple[str, str, int | None, bool]]:
    pieces: list[tuple[str, str, int | None, bool]] = []
    for sec, path in _iter_sections(doc.sections, []):
        pieces.append((sec.text.strip(), path, sec.page, sec.is_table))
    return pieces


# ---------- fixed / recursive（消融基线，忽略结构） ----------
def _flat_text(doc: ParsedDocument) -> str:
    lines: list[str] = []

    def walk(nodes: list[Section]) -> None:
        for n in nodes:
            lines.append(n.title)
            if n.text.strip():
                lines.append(n.text.strip())
            walk(n.children)

    walk(doc.sections)
    return "\n".join(lines)


def _fixed_pieces(doc: ParsedDocument) -> list[tuple[str, str, int | None, bool]]:
    text = _flat_text(doc)
    step = max(1, 1)  # 由 _assemble 按 settings 处理
    return [(text, "", None, False)] if False else [(text[i:], "", None, False) for i in range(0)]  # 占位由 assemble 处理


def _recursive_pieces(doc: ParsedDocument) -> list[tuple[str, str, int | None, bool]]:
    return [(_flat_text(doc), "", None, False)]
```

> 注意：fixed/recursive 的窗口切分统一放到 `_assemble` 中处理更干净——`_structural` 产出「已按结构对齐的 piece」，fixed/recursive 产出「单个大 piece + 标记」，由 `_assemble` 分别应用「句聚合」或「滑窗/递归」逻辑。**实现时删除上面的占位代码**，最终版如下。

最终版 `_assemble` 与基线策略：

```python
def _assemble(doc: ParsedDocument, pieces, settings: ChunkingSettings) -> list[Chunk]:
    chunks: list[Chunk] = []
    seq = 0

    def push(text: str, path: str, page: int | None) -> None:
        nonlocal seq
        text = text.strip()
        if not text:
            return
        # 尾块过短并入前块
        if chunks and len(text) < settings.min_chars and chunks[-1].section_path == path:
            chunks[-1].text = f"{chunks[-1].text}\n{text}"
            return
        chunks.append(Chunk(chunk_id=f"{doc.doc_hash[:12]}-{seq:04d}", doc_hash=doc.doc_hash,
                            text=text, section_path=path, page=page, seq=seq))
        seq += 1

    for text, path, page, is_table in pieces:
        if is_table:
            for part in _split_table(text, settings):
                push(part, path, page)
        elif settings.strategy == "structural":
            for part in _split_sentences(text, settings):
                push(part, path, page)
        else:
            # fixed / recursive 基线：全文 piece 走对应切分
            splitter = _sliding_window if settings.strategy == "fixed" else _recursive_split
            for part in splitter(text, settings):
                push(part, path, page)
    return chunks


def _split_sentences(text: str, s: ChunkingSettings) -> list[str]:
    parts, buf = [], ""
    for seg in _iter_sentences(text):
        if len(buf) + len(seg) > s.max_chars and buf:
            parts.append(buf)
            buf = buf[-s.overlap :] + seg if s.overlap else seg
        else:
            buf += seg
    if buf:
        parts.append(buf)
    return parts


def _iter_sentences(text: str) -> Iterator[str]:
    buf = ""
    for ch in text:
        buf += ch
        if ch in _SENTENCE_BREAKS:
            yield buf
            buf = ""
    if buf:
        yield buf


def _split_table(md: str, s: ChunkingSettings) -> list[str]:
    lines = md.splitlines()
    if len("\n".join(lines)) <= s.table_max_chars or len(lines) <= 3:
        return [md]
    header = lines[0]
    parts, buf = [], [header]
    for line in lines[1:]:
        buf.append(line)
        if len("\n".join(buf)) > s.table_max_chars:
            parts.append("\n".join(buf))
            buf = [header]
    if len(buf) > 1:
        parts.append("\n".join(buf))
    return parts


def _sliding_window(text: str, s: ChunkingSettings) -> list[str]:
    step = max(1, s.max_chars - s.overlap)
    return [text[i : i + s.max_chars] for i in range(0, max(len(text), 1), step) if text[i : i + s.max_chars].strip()]


def _recursive_split(text: str, s: ChunkingSettings) -> list[str]:
    for sep in ["\n\n", "\n", "。", "；", "，"]:
        segs = [x for x in text.split(sep)]
        out, buf = [], ""
        for seg in segs:
            cand = buf + sep + seg if buf else seg
            if len(cand) > s.max_chars and buf:
                out.append(buf)
                buf = seg
            else:
                buf = cand
        text_remaining = None  # noqa: F841
        if buf:
            out.append(buf)
        if all(len(p) <= s.max_chars for p in out) or sep == "，":
            return out
        text = sep.join(out)  # 不再收敛则交给下一分隔符
    return _sliding_window(text, s)
```

（实现时以「测试通过 + 可读性」为准微调 `_recursive_split` 的收敛处理。）

- [ ] **Step 2: 测试 `backend/tests/test_chunking.py`**

```python
from app.core.config import ChunkingSettings
from app.ingestion.models import ParsedDocument, Section


def _doc():
    s21 = Section(level=2, title="用法用量", text="口服。" * 300)  # 900 字
    return ParsedDocument(source_path="x", doc_type="drug_label", department="心血管",
                          title="药", doc_hash="a" * 16,
                          sections=[Section(level=1, title="阿司匹林", children=[
                              Section(level=2, title="适应证", text="预防心肌梗死。"),
                              s21,
                              Section(level=2, title="表", is_table=True,
                                      text="|药|量|\n|---|---|\n|A|100|"),
                          ])])


def test_structural_keeps_path_and_table():
    chunks = chunk_document(_doc(), ChunkingSettings(strategy="structural"))
    assert any("适应证" in c.section_path for c in chunks)
    assert any(c.text.startswith("|药|量|") for c in chunks)
    longs = [c for c in chunks if "用法用量" in c.section_path and "口服" in c.text]
    assert len(longs) >= 2 and all(len(c.text) <= 700 for c in longs)
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))


def test_fixed_strategy_flat_window():
    chunks = chunk_document(_doc(), ChunkingSettings(strategy="fixed", max_chars=200, overlap=50))
    assert all(len(c.text) <= 200 for c in chunks)
    assert chunks[0].section_path == ""  # 基线无结构信息


def test_recursive_strategy_respects_max():
    chunks = chunk_document(_doc(), ChunkingSettings(strategy="recursive", max_chars=300))
    assert chunks and all(len(c.text) <= 320 for c in chunks)


def test_small_tail_merged():
    chunks = chunk_document(_doc(), ChunkingSettings(strategy="structural"))
    texts = [c.text for c in chunks if "预防心肌梗死" in c.text]
    assert len(texts) == 1
```

（`from app.ingestion.chunking import chunk_document` 补进导入。）

- [ ] **Step 3: pytest/ruff/mypy 全绿 → Commit** `feat: 三种分块策略（structural/fixed/recursive）`

---

### Task 6: MilvusStore（collection schema + BM25 + 幂等 upsert）

**Files:**
- Create: `backend/app/ingestion/store.py`
- Test: `backend/tests/test_store.py`（mock MilvusClient）

**Interfaces:**
- Consumes: `Settings.milvus_uri / milvus_collection`、`Chunk`、pymilvus `MilvusClient/DataType/Function`
- Produces:
  - `MilvusStore(uri: str, collection: str = "medical_chunks", dim: int = 1024, client: MilvusClient | None = None)`
  - `ensure_collection(recreate: bool = False) -> None`：字段 `chunk_id`(PK,varchar64)、`text`(varchar8192, enable_analyzer, jieba)、`dense`(float_vector dim)、`sparse`(sparse_float_vector, BM25 函数输出)、`doc_hash`(64)、`doc_type`(32)、`department`(32)、`source`(512)、`section_path`(512)、`page`(int64)、`seq`(int64)；索引 dense=HNSW/COSINE(M=16,efConstruction=200)、sparse=SPARSE_INVERTED_INDEX/BM25
  - `upsert_document(meta: DocumentMeta, rows: list[dict]) -> int`：先 `delete(expr=f'doc_hash == "{meta.doc_hash}"')` 再 `insert`，返回插入行数。`DocumentMeta` 为 `(doc_hash, doc_type, department, source)` 的 dataclass/pydantic
  - `count() -> int`
  - mock 测试验证：schema 字段齐、insert 前有 delete 调用、recreate 会 drop_collection

- [ ] **Step 1: 实现 `backend/app/ingestion/store.py`**

```python
from typing import Any

from pymilvus import DataType, Function, FunctionType, MilvusClient


class DocumentMeta:
    def __init__(self, doc_hash: str, doc_type: str, department: str, source: str) -> None:
        self.doc_hash, self.doc_type = doc_hash, doc_type
        self.department, self.source = department, source


class MilvusStore:
    """Milvus 混合索引存储：dense(HNSW/COSINE) + BM25(jieba) sparse + 标量元数据。"""

    def __init__(self, uri: str, collection: str = "medical_chunks", dim: int = 1024,
                 client: Any | None = None) -> None:
        self._client = client or MilvusClient(uri=uri)
        self._collection = collection
        self._dim = dim

    def ensure_collection(self, recreate: bool = False) -> None:
        if recreate and self._client.has_collection(self._collection):
            self._client.drop_collection(self._collection)
        if self._client.has_collection(self._collection):
            return
        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("chunk_id", DataType.VARCHAR, is_primary=True, max_length=64)
        schema.add_field("text", DataType.VARCHAR, max_length=8192,
                         enable_analyzer=True, analyzer_params={"tokenizer": "jieba"})
        schema.add_field("dense", DataType.FLOAT_VECTOR, dim=self._dim)
        schema.add_field("sparse", DataType.SPARSE_FLOAT_VECTOR)
        schema.add_field("doc_hash", DataType.VARCHAR, max_length=64)
        schema.add_field("doc_type", DataType.VARCHAR, max_length=32)
        schema.add_field("department", DataType.VARCHAR, max_length=32)
        schema.add_field("source", DataType.VARCHAR, max_length=512)
        schema.add_field("section_path", DataType.VARCHAR, max_length=512)
        schema.add_field("page", DataType.INT64)
        schema.add_field("seq", DataType.INT64)
        schema.add_function(Function(
            name="text_bm25", input_field_names=["text"], output_field_names=["sparse"],
            function_type=FunctionType.BM25,
        ))
        index = self._client.prepare_index_params()
        index.add_index(field_name="dense", index_type="HNSW", metric_type="COSINE",
                        params={"M": 16, "efConstruction": 200})
        index.add_index(field_name="sparse", index_type="SPARSE_INVERTED_INDEX",
                        metric_type="BM25")
        self._client.create_collection(self._collection, schema=schema, index_params=index)

    def upsert_document(self, meta: DocumentMeta, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        self._client.delete(collection_name=self._collection,
                            filter=f'doc_hash == "{meta.doc_hash}"')
        enriched = [{**r, "doc_hash": meta.doc_hash, "doc_type": meta.doc_type,
                     "department": meta.department, "source": meta.source} for r in rows]
        self._client.insert(collection_name=self._collection, data=enriched)
        return len(enriched)

    def count(self) -> int:
        stats = self._client.get_collection_stats(self._collection)
        return int(stats.get("row_count", 0))
```

- [ ] **Step 2: mock 测试 `backend/tests/test_store.py`**

```python
from app.ingestion.store import DocumentMeta, MilvusStore


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.collections: set[str] = set()

    def has_collection(self, name): 
        self.calls.append(("has_collection", {"name": name}))
        return name in self.collections

    def drop_collection(self, name):
        self.calls.append(("drop", {"name": name}))
        self.collections.discard(name)

    def create_schema(self, **kw):
        from pymilvus import MilvusClient
        return MilvusClient.create_schema(**kw)

    def prepare_index_params(self):
        from pymilvus import MilvusClient
        return MilvusClient.prepare_index_params()

    def create_collection(self, name, schema=None, index_params=None):
        self.calls.append(("create", {"name": name}))
        self.created_schema = schema
        self.collections.add(name)

    def delete(self, collection_name, filter):
        self.calls.append(("delete", {"col": collection_name, "filter": filter}))

    def insert(self, collection_name, data):
        self.calls.append(("insert", {"col": collection_name, "n": len(data)}))
        self.inserted = data

    def get_collection_stats(self, name):
        return {"row_count": 42}


def test_ensure_collection_creates_with_bm25():
    fake = FakeClient()
    store = MilvusStore("http://x", client=fake)
    store.ensure_collection()
    assert fake.calls[0][0] == "has_collection"
    assert fake.calls[-1][0] == "create"
    fields = {f["name"] for f in fake.created_schema.to_dict()["fields"]}
    assert {"chunk_id", "text", "dense", "sparse", "doc_hash", "department"} <= fields


def test_upsert_deletes_then_inserts():
    fake = FakeClient()
    fake.collections.add("medical_chunks")
    store = MilvusStore("http://x", client=fake)
    meta = DocumentMeta("h1" * 5, "guideline", "心血管", "x.pdf")
    n = store.upsert_document(meta, [{"chunk_id": "c1", "text": "t", "dense": [0.1] * 1024,
                                      "section_path": "", "page": 1, "seq": 0}])
    assert n == 1
    kinds = [c[0] for c in fake.calls]
    assert kinds.index("delete") < kinds.index("insert")
    assert fake.inserted[0]["department"] == "心血管"


def test_recreate_drops_existing():
    fake = FakeClient()
    fake.collections.add("medical_chunks")
    store = MilvusStore("http://x", client=fake)
    store.ensure_collection(recreate=True)
    assert any(c[0] == "drop" for c in fake.calls)
```

- [ ] **Step 3: pytest/ruff/mypy 全绿 → Commit** `feat: MilvusStore 混合索引存储（BM25 jieba + HNSW + 幂等 upsert）`

---

### Task 7: Embedding 批处理封装

**Files:**
- Create: `backend/app/ingestion/embedder.py`
- Test: `backend/tests/test_embedder.py`

**Interfaces:**
- Consumes: `EmbeddingProvider`（P1）
- Produces: `EmbeddingBatcher(provider: EmbeddingProvider | None = None, batch_size: int = 32)`、`async embed(texts: list[str]) -> list[list[float]]`（保持顺序、逐批打日志、空输入返回空）

- [ ] **Step 1: 实现**

```python
from loguru import logger

from app.core.providers import get_embedding_provider
from app.core.providers.embedding import EmbeddingProvider


class EmbeddingBatcher:
    """文本批量向量化：按 batch_size 分批调用（SiliconFlow 单批上限），保序返回。"""

    def __init__(self, provider: EmbeddingProvider | None = None, batch_size: int = 32) -> None:
        self._provider = provider or get_embedding_provider()
        self._batch_size = batch_size

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            vectors.extend(await self._provider.embed(batch))
            logger.info("embedding {}/{}", min(start + self._batch_size, len(texts)), len(texts))
        return vectors
```

- [ ] **Step 2: 测试（fake provider，验证保序与分批）**

```python
from app.core.providers.embedding import EmbeddingProvider
from app.ingestion.embedder import EmbeddingBatcher


class SeqProvider(EmbeddingProvider):
    def __init__(self) -> None:
        self.batches: list[int] = []

    async def embed(self, texts):
        self.batches.append(len(texts))
        return [[float(i)] for i in range(len(texts))]


async def test_batches_preserve_order():
    p = SeqProvider()
    batcher = EmbeddingBatcher(provider=p, batch_size=4)
    vecs = await batcher.embed([f"t{i}" for i in range(10)])
    assert p.batches == [4, 4, 2]
    assert [v[0] for v in vecs] == [0, 1, 2, 3, 0, 1, 2, 3, 0, 1]  # 每批内部从0计数


async def test_empty_input():
    batcher = EmbeddingBatcher(provider=SeqProvider(), batch_size=4)
    assert await batcher.embed([]) == []
```

（`SeqProvider` 直接继承覆盖 `embed` 即可，不走父类 `__init__`。）

- [ ] **Step 3: pytest/ruff/mypy 全绿 → Commit** `feat: Embedding 批处理封装`

---

### Task 8: Ingest CLI（编排 + IngestJob 记录）

**Files:**
- Create: `backend/app/ingestion/__main__.py`
- Create: `backend/app/ingestion/pipeline.py`（编排核心，CLI 与未来 P5 API 共用）
- Test: `backend/tests/test_pipeline.py`（fake store + fake batcher，不碰真实 Milvus）

**Interfaces:**
- Consumes: 全部前序（parsers/chunking/store/embedder）、`IngestJob` 模型、`get_session_factory`
- Produces:
  - `scan_files(root: Path) -> list[Path]`（遍历支持的 7 种后缀）
  - `async run_ingestion(data_root: Path, *, strategy: str | None, dry_run: bool, limit: int | None, recreate: bool, store: MilvusStore | None = None, batcher: EmbeddingBatcher | None = None) -> IngestStats`
  - `IngestStats(total_docs, processed_docs, total_chunks, errors: list[str])`
  - CLI 参数：`--dir`（默认 `../data/raw` 相对 backend，也接受绝对路径）、`--strategy`、`--dry-run`、`--limit`、`--recreate`
  - 行为：逐文件 parse → chunk → dry_run 则只统计；否则 embed → store.upsert；IngestJob 记录（MySQL 不可用时 warning 不阻塞）；单文件失败记入 errors 继续处理后续文件

- [ ] **Step 1: 实现 `pipeline.py`**

```python
import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from app.core.config import get_settings
from app.ingestion.chunking import chunk_document
from app.ingestion.embedder import EmbeddingBatcher
from app.ingestion.parsers import get_parser
from app.ingestion.registry import department_for, doc_type_for
from app.ingestion.store import DocumentMeta, MilvusStore

SUPPORTED_SUFFIXES = {".pdf", ".md", ".html", ".htm", ".docx", ".json", ".csv"}


@dataclass
class IngestStats:
    total_docs: int = 0
    processed_docs: int = 0
    total_chunks: int = 0
    errors: list[str] = field(default_factory=list)


def scan_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*")
                  if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES)


async def run_ingestion(data_root: Path, *, strategy: str | None = None, dry_run: bool = False,
                        limit: int | None = None, recreate: bool = False,
                        store: MilvusStore | None = None, batcher: EmbeddingBatcher | None = None
                        ) -> IngestStats:
    settings = get_settings()
    files = scan_files(data_root)
    if limit:
        files = files[:limit]
    stats = IngestStats(total_docs=len(files))
    if dry_run:
        for f in files:
            try:
                doc = get_parser(f).parse(f, department=department_for(f, data_root),
                                          source_path=str(f))
                n = len(chunk_document(doc, settings.chunking))
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
    chunk_cfg = settings.chunking.model_copy(update={"strategy": strategy}) if strategy else settings.chunking

    async def process_one(f: Path) -> None:
        doc = get_parser(f).parse(f, department=department_for(f, data_root), source_path=str(f))
        chunks = chunk_document(doc, chunk_cfg)
        vectors = await active_batcher.embed([c.text for c in chunks])
        rows = [{"chunk_id": c.chunk_id, "text": c.text, "dense": v,
                 "section_path": c.section_path or "", "page": c.page or 0, "seq": c.seq}
                for c, v in zip(chunks, vectors, strict=True)]
        meta = DocumentMeta(doc.doc_hash, doc.doc_type or doc_type_for(f.suffix), doc.department, doc.source_path)
        n = active_store.upsert_document(meta, rows)
        stats.processed_docs += 1
        stats.total_chunks += n
        logger.info("入库 {} -> {} chunks", f.name, n)

    for f in files:
        try:
            await process_one(f)
        except Exception as exc:
            stats.errors.append(f"{f}: {exc}")
            logger.exception("处理失败 {}", f)
    _record_job(stats)
    return stats


def _record_job(stats: IngestStats) -> None:
    """IngestJob 落库（MySQL 不可用时降级为日志，不阻塞入库）。"""
    try:
        from app.core.db import get_session_factory
        from app.models import IngestJob

        settings = get_settings()
        factory = get_session_factory(settings.database_url)

        async def _write() -> None:
            async with factory() as session:
                session.add(IngestJob(status="failed" if stats.errors else "completed",
                                      total_docs=stats.total_docs,
                                      processed_docs=stats.processed_docs,
                                      total_chunks=stats.total_chunks,
                                      error="; ".join(stats.errors[:5]) or None))
                await session.commit()

        asyncio.get_running_loop().create_task(_write())
    except Exception as exc:
        logger.warning("IngestJob 记录失败（忽略）: {}", exc)
```

- [ ] **Step 2: CLI `__main__.py`**

```python
import argparse
import asyncio
import sys
from pathlib import Path

from app.core.logging import setup_logging
from app.ingestion.pipeline import run_ingestion


def main() -> int:
    ap = argparse.ArgumentParser(prog="app.ingestion", description="MedicalRAG 知识入库管线")
    ap.add_argument("--dir", default="../data/raw", help="数据目录（默认 ../data/raw）")
    ap.add_argument("--strategy", choices=["structural", "fixed", "recursive"], default=None)
    ap.add_argument("--dry-run", action="store_true", help="只解析分块并统计，不写库")
    ap.add_argument("--limit", type=int, default=None, help="只处理前 N 个文件")
    ap.add_argument("--recreate", action="store_true", help="删除并重建 collection")
    args = ap.parse_args()

    setup_logging()
    data_root = Path(args.dir).resolve()
    if not data_root.is_dir():
        print(f"数据目录不存在: {data_root}", file=sys.stderr)
        return 2
    stats = asyncio.run(run_ingestion(data_root, strategy=args.strategy, dry_run=args.dry_run,
                                      limit=args.limit, recreate=args.recreate))
    print(f"\n完成：{stats.processed_docs}/{stats.total_docs} 文档，"
          f"{stats.total_chunks} chunks，错误 {len(stats.errors)} 个")
    for e in stats.errors[:10]:
        print(f"  - {e}")
    return 0 if not stats.errors else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: 测试 `backend/tests/test_pipeline.py`（fake store/batcher，tmp 目录真文件）**

```python
from pathlib import Path

from app.core.config import ChunkingSettings
from app.ingestion.embedder import EmbeddingBatcher
from app.ingestion.pipeline import run_ingestion, scan_files


class FakeStore:
    def __init__(self) -> None:
        self.docs: list[tuple[str, int]] = []

    def ensure_collection(self, recreate=False): ...

    def upsert_document(self, meta, rows):
        self.docs.append((meta.doc_hash, len(rows)))
        return len(rows)


class FakeBatcher(EmbeddingBatcher):
    def __init__(self) -> None:
        pass

    async def embed(self, texts):
        return [[0.0] * 8 for _ in texts]


def _data(tmp_path: Path) -> Path:
    d = tmp_path / "raw" / "markdown" / "心血管"
    d.mkdir(parents=True)
    (d / "g.md").write_text("# 指南\n\n## 一\n\n内容A。\n\n## 二\n\n内容B。", encoding="utf-8")
    (tmp_path / "raw" / "ignored.txt").write_text("skip", encoding="utf-8")
    return tmp_path / "raw"


def test_scan_filters_suffixes(tmp_path: Path):
    root = _data(tmp_path)
    files = scan_files(root)
    assert [f.name for f in files] == ["g.md"]


async def test_run_ingestion_dry_run(tmp_path: Path):
    stats = await run_ingestion(_data(tmp_path), dry_run=True)
    assert stats.total_docs == 1 and stats.processed_docs == 1
    assert stats.total_chunks >= 2 and not stats.errors


async def test_run_ingestion_with_fakes(tmp_path: Path):
    store, batcher = FakeStore(), FakeBatcher()
    stats = await run_ingestion(_data(tmp_path), store=store, batcher=batcher)  # type: ignore[arg-type]
    assert stats.processed_docs == 1
    assert store.docs and store.docs[0][1] == stats.total_chunks
    assert len(stats.errors) == 0
```

> 注：测试环境中 MySQL 不通，`_record_job` 走 warning 降级——断言不受影响。`asyncio.get_running_loop().create_task` 在事件循环结束时任务可能未完成；实现时改为直接 `asyncio.create_task` + 在 run_ingestion 结尾 `await asyncio.gather(*pending)`，或干脆同步写（在 pipeline 里 `await _write()`）。**实现取「直接 await 写库」**，代码相应调整。

- [ ] **Step 4: pytest/ruff/mypy 全绿 → Commit** `feat: Ingest 编排管线与 CLI`

---

### Task 9: 样例数据集 + 端到端冒烟验证（真实 Milvus + 真实 Embedding）

**Files:**
- Create: `data/samples/guideline_hypertension.md`（合成中文高血压指南：多级标题+表格+列表，~150 行）
- Create: `data/samples/drug_label_aspirin.json`（阿司匹林说明书样例，约定字段）
- Create: `data/samples/sample_page.html`（简单医学页面）
- Create: `data/raw/README.md`（数据放置规范说明）
- Create: `scripts/probe_search.py`（入库后检索冒烟：dense + BM25 各查一次）
- Modify: `README.md`（P2 状态与用法）

**Interfaces:**
- Consumes: 全部前序
- Produces: 可复制的入库冒烟流程；`make ingest-samples`、`make probe q="查询词"` Makefile 目标

- [ ] **Step 1: 写样例文件**（内容见执行时生成，规范：md 多级标题含表格；json 遵循 `{"name","department","fields"}`；html 单页 h1/h2/p）

- [ ] **Step 2: `scripts/probe_search.py`**

```python
"""检索冒烟：对 medical_chunks 分别做 dense 与 BM25 查询，各打印 top-3。

用法：make probe q="阿司匹林剂量"（需先入库并配置真实 EMBEDDING key）
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.core.providers.embedding import EmbeddingProvider  # noqa: E402


async def main() -> int:
    query = sys.argv[1] if len(sys.argv) > 1 else "高血压的诊断标准是什么"
    s = get_settings()
    from pymilvus import MilvusClient

    client = MilvusClient(uri=s.milvus_uri)
    col = s.milvus_collection
    if not client.has_collection(col):
        print(f"collection {col} 不存在，请先入库")
        return 2
    client.load_collection(col)

    vec = (await EmbeddingProvider(s.embedding).embed([query]))[0]
    dense_hits = client.search(col, data=[vec], anns_field="dense", limit=3,
                               output_fields=["text", "section_path"],
                               search_params={"metric_type": "COSINE"})
    print("== dense top3 ==")
    for hit in dense_hits[0]:
        print(f"  {hit['distance']:.3f} [{hit['entity']['section_path']}] {hit['entity']['text'][:60]}")

    sparse_hits = client.search(col, data=[query], anns_field="sparse", limit=3,
                                output_fields=["text", "section_path"])
    print("== BM25 top3 ==")
    for hit in sparse_hits[0]:
        print(f"  {hit['distance']:.3f} [{hit['entity']['section_path']}] {hit['entity']['text'][:60]}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 3: Makefile 增加目标**

```makefile
ingest-samples:
	cd backend && uv run python -m app.ingestion --dir ../data/samples

probe:
	cd backend && uv run python ../scripts/probe_search.py "$(q)"
```

- [ ] **Step 4: 端到端冒烟（本机，Milvus 已在跑）**

```bash
export PATH="$HOME/.local/bin:$PATH"
cd backend
uv run python -m app.ingestion --dir ../data/samples --dry-run    # 期望：N 文档、M chunks、0 错误
uv run python -m app.ingestion --dir ../data/samples              # 真实 embed + 写入
uv run python ../scripts/probe_search.py "高血压的诊断标准"        # dense 与 BM25 各有合理 top3
uv run python -m app.ingestion --dir ../data/samples              # 幂等：重复入库后 probe 结果不变、行数不翻倍
```

- [ ] **Step 5: 全量门禁 + 更新 README（P2 勾选 + 数据放置指引）→ Commit** `feat: 样例数据集与端到端冒烟（P2 收尾）`

---

## 任务依赖

```
T1 ─▶ T2 ─▶ T3 ─▶ T4 ─▶ T5 ─▶ T6 ─▶ T7 ─▶ T8 ─▶ T9
```

T6 只依赖 T1（Chunk 模型）；T3/T4 依赖 T2（SectionTreeBuilder）；T5 依赖 T1；T8 汇合全部。
