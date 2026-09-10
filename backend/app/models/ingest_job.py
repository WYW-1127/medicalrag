from typing import Any

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class IngestJob(Base, TimestampMixin):
    __tablename__ = "ingest_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    total_docs: Mapped[int] = mapped_column(default=0)
    processed_docs: Mapped[int] = mapped_column(default=0)
    total_chunks: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    stats: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
