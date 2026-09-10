from dataclasses import dataclass
from typing import Any

from pymilvus import DataType, Function, FunctionType, MilvusClient


@dataclass
class DocumentMeta:
    """文档级元数据，随该文档所有 chunk 一并写入。"""

    doc_hash: str
    doc_type: str
    department: str
    source: str


class MilvusStore:
    """Milvus 混合索引存储：dense(HNSW/COSINE) + BM25(jieba) sparse + 标量元数据。

    幂等策略：upsert 前按 doc_hash 删除旧 chunk，再整批重插——同一文档重复入库
    不会产生重复数据（chunk_id 本身也确定性生成）。
    """

    def __init__(
        self,
        uri: str,
        collection: str = "medical_chunks",
        dim: int = 1024,
        client: Any | None = None,
    ) -> None:
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
        schema.add_field(
            "text",
            DataType.VARCHAR,
            max_length=8192,
            enable_analyzer=True,
            analyzer_params={"tokenizer": "jieba"},
        )
        schema.add_field("dense", DataType.FLOAT_VECTOR, dim=self._dim)
        schema.add_field("sparse", DataType.SPARSE_FLOAT_VECTOR)
        schema.add_field("doc_hash", DataType.VARCHAR, max_length=64)
        schema.add_field("doc_type", DataType.VARCHAR, max_length=32)
        schema.add_field("department", DataType.VARCHAR, max_length=32)
        schema.add_field("source", DataType.VARCHAR, max_length=512)
        schema.add_field("section_path", DataType.VARCHAR, max_length=512)
        schema.add_field("page", DataType.INT64)
        schema.add_field("seq", DataType.INT64)
        # BM25 函数：写入时由 text 自动生成 sparse 向量（中文 jieba 分词）
        schema.add_function(
            Function(
                name="text_bm25",
                input_field_names=["text"],
                output_field_names=["sparse"],
                function_type=FunctionType.BM25,
            )
        )
        index = self._client.prepare_index_params()
        index.add_index(
            field_name="dense",
            index_type="HNSW",
            metric_type="COSINE",
            params={"M": 16, "efConstruction": 200},
        )
        index.add_index(
            field_name="sparse",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="BM25",
        )
        self._client.create_collection(self._collection, schema=schema, index_params=index)

    def upsert_document(self, meta: DocumentMeta, rows: list[dict[str, Any]]) -> int:
        """删除该文档旧 chunk 后整批重插；rows 不含 sparse（BM25 函数自动生成）。"""
        if not rows:
            return 0
        self._client.delete(
            collection_name=self._collection, filter=f'doc_hash == "{meta.doc_hash}"'
        )
        enriched = [
            {
                **r,
                "doc_hash": meta.doc_hash,
                "doc_type": meta.doc_type,
                "department": meta.department,
                "source": meta.source,
            }
            for r in rows
        ]
        self._client.insert(collection_name=self._collection, data=enriched)
        return len(enriched)

    def count(self) -> int:
        stats = self._client.get_collection_stats(self._collection)
        return int(stats.get("row_count", 0))
