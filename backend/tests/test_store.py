from typing import Any

from app.ingestion.store import DocumentMeta, MilvusStore


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.collections: set[str] = set()
        self.inserted: list[dict] = []
        self.created_schema: Any = None

    def has_collection(self, name: str) -> bool:
        self.calls.append(("has_collection", {"name": name}))
        return name in self.collections

    def drop_collection(self, name: str) -> None:
        self.calls.append(("drop", {"name": name}))
        self.collections.discard(name)

    def create_schema(self, **kwargs: Any) -> Any:
        return MilvusClient.create_schema(**kwargs)

    def prepare_index_params(self) -> Any:
        return MilvusClient.prepare_index_params()

    def create_collection(self, name: str, schema: Any = None, index_params: Any = None) -> None:
        self.calls.append(("create", {"name": name}))
        self.created_schema = schema
        self.collections.add(name)

    def delete(self, collection_name: str, filter: str) -> None:  # noqa: A002
        self.calls.append(("delete", {"col": collection_name, "filter": filter}))

    def insert(self, collection_name: str, data: list[dict]) -> None:
        self.calls.append(("insert", {"col": collection_name, "n": len(data)}))
        self.inserted = data

    def get_collection_stats(self, name: str) -> dict:
        return {"row_count": 42}


from pymilvus import MilvusClient  # noqa: E402


def test_ensure_collection_creates_with_fields():
    fake = FakeClient()
    store = MilvusStore("http://x", client=fake)
    store.ensure_collection()
    assert fake.calls[0][0] == "has_collection"
    assert fake.calls[-1][0] == "create"
    fields = {f["name"] for f in fake.created_schema.to_dict()["fields"]}
    assert {"chunk_id", "text", "dense", "sparse", "doc_hash", "department"} <= fields


def test_ensure_collection_idempotent():
    fake = FakeClient()
    fake.collections.add("medical_chunks")
    store = MilvusStore("http://x", client=fake)
    store.ensure_collection()
    assert not any(c[0] == "create" for c in fake.calls)


def test_upsert_deletes_then_inserts():
    fake = FakeClient()
    fake.collections.add("medical_chunks")
    store = MilvusStore("http://x", client=fake)
    meta = DocumentMeta("h1" * 5, "guideline", "心血管", "x.pdf")
    n = store.upsert_document(
        meta,
        [
            {
                "chunk_id": "c1",
                "text": "高血压诊断标准",
                "dense": [0.1] * 1024,
                "section_path": "",
                "page": 1,
                "seq": 0,
            }
        ],
    )
    assert n == 1
    kinds = [c[0] for c in fake.calls]
    assert kinds.index("delete") < kinds.index("insert")
    assert fake.inserted[0]["department"] == "心血管"
    assert "sparse" not in fake.inserted[0]  # sparse 由 BM25 函数生成，不手写


def test_upsert_empty_rows_noop():
    fake = FakeClient()
    store = MilvusStore("http://x", client=fake)
    assert store.upsert_document(DocumentMeta("h", "g", "综合", "x"), []) == 0
    assert not any(c[0] in ("delete", "insert") for c in fake.calls)


def test_recreate_drops_existing():
    fake = FakeClient()
    fake.collections.add("medical_chunks")
    store = MilvusStore("http://x", client=fake)
    store.ensure_collection(recreate=True)
    assert any(c[0] == "drop" for c in fake.calls)
    assert any(c[0] == "create" for c in fake.calls)
