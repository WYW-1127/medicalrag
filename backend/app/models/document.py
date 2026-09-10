from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Document(Base, TimestampMixin):
    """知识库文档登记表：GET /documents 数据源（ingestion 时同步写入）。"""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    doc_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(512))
    title: Mapped[str] = mapped_column(String(256), default="")
    doc_type: Mapped[str] = mapped_column(String(32), default="guideline")
    department: Mapped[str] = mapped_column(String(32), default="综合")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
