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
