from collections.abc import Iterator
from typing import NamedTuple

from app.core.config import ChunkingSettings
from app.ingestion.models import Chunk, ParsedDocument, Section

_SENTENCE_BREAKS = "。；！？\n"


class _Piece(NamedTuple):
    """待装配的文本片段：正文或表格，连同其章节路径。"""

    text: str
    path: str
    page: int | None
    is_table: bool


def chunk_document(doc: ParsedDocument, settings: ChunkingSettings) -> list[Chunk]:
    """按策略分块。structural 保留章节路径与表格完整性；fixed/recursive 为消融基线。"""
    if settings.strategy == "structural":
        pieces = _structural_pieces(doc)
        split = "sentence"
    elif settings.strategy == "fixed":
        pieces = _baseline_piece(doc)
        split = "window"
    elif settings.strategy == "recursive":
        pieces = _baseline_piece(doc)
        split = "recursive"
    else:
        raise ValueError(f"未知分块策略: {settings.strategy}")
    return _assemble(doc, pieces, settings, split)


# ---------- structural：遍历 Section 树 ----------
def _iter_sections(nodes: list[Section], path: list[str]) -> Iterator[tuple[Section, str]]:
    for node in nodes:
        cur = [*path, node.title]
        if node.text.strip() or node.is_table:
            yield node, " > ".join(cur)
        yield from _iter_sections(node.children, cur)


def _structural_pieces(doc: ParsedDocument) -> list[_Piece]:
    return [
        _Piece(sec.text.strip(), path, sec.page, sec.is_table)
        for sec, path in _iter_sections(doc.sections, [])
    ]


# ---------- fixed / recursive 基线：忽略结构拍平 ----------
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


def _baseline_piece(doc: ParsedDocument) -> list[_Piece]:
    return [_Piece(_flat_text(doc), "", None, False)]


# ---------- 装配 ----------
def _assemble(
    doc: ParsedDocument, pieces: list[_Piece], settings: ChunkingSettings, split: str
) -> list[Chunk]:
    chunks: list[Chunk] = []
    seq = 0

    def push(text: str, path: str, page: int | None) -> None:
        nonlocal seq
        text = text.strip()
        if not text:
            return
        # 尾块过短并入前块（同路径且不超限时），避免碎片 chunk
        if (
            chunks
            and len(text) < settings.min_chars
            and chunks[-1].section_path == path
            and not chunks[-1].text.startswith("|")
            and len(chunks[-1].text) + 1 + len(text) <= settings.max_chars
        ):
            chunks[-1].text = f"{chunks[-1].text}\n{text}"
            return
        chunks.append(
            Chunk(
                chunk_id=f"{doc.doc_hash[:12]}-{seq:04d}",
                doc_hash=doc.doc_hash,
                text=text,
                section_path=path,
                page=page,
                seq=seq,
            )
        )
        seq += 1

    for piece in pieces:
        if piece.is_table:
            parts = _split_table(piece.text, settings)
        elif split == "sentence":
            parts = _split_sentences(piece.text, settings)
        elif split == "window":
            parts = _sliding_window(piece.text, settings)
        else:
            parts = _recursive_split(piece.text, settings)
        for part in parts:
            push(part, piece.path, piece.page)
    return chunks


# ---------- 切分器 ----------
def _split_sentences(text: str, s: ChunkingSettings) -> list[str]:
    parts: list[str] = []
    buf = ""
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
    header, parts, buf = lines[0], [], [lines[0]]
    for line in lines[1:]:
        buf.append(line)
        if len("\n".join(buf)) > s.table_max_chars:
            parts.append("\n".join(buf))
            buf = [header]  # 后续分片重复表头，保证块内自解释
    if len(buf) > 1:
        parts.append("\n".join(buf))
    return parts


def _sliding_window(text: str, s: ChunkingSettings) -> list[str]:
    step = max(1, s.max_chars - s.overlap)
    return [
        piece
        for i in range(0, max(len(text), 1), step)
        if (piece := text[i : i + s.max_chars]).strip()
    ]


def _recursive_split(text: str, s: ChunkingSettings) -> list[str]:
    current = text
    for sep in ["\n\n", "\n", "。", "；", "，"]:
        out: list[str] = []
        buf = ""
        for seg in current.split(sep):
            cand = buf + sep + seg if buf else seg
            if len(cand) > s.max_chars and buf:
                out.append(buf)
                buf = seg
            else:
                buf = cand
        if buf:
            out.append(buf)
        if all(len(p) <= s.max_chars for p in out):
            return out
        # 仍有超长片段：用更细的分隔符重新切（拼接后保序）
        current = sep.join(out)
    return _sliding_window(current, s)
