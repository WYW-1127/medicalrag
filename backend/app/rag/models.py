from pydantic import BaseModel, Field


class RetrievedChunk(BaseModel):
    """检索结果单元：来自 Milvus 的一个 chunk 及其各阶段分数。

    dense_score/sparse_score 是召回分数（来源各自的检索路），
    fused_score 是融合分数，rerank_score 是精排分数——保留全部分数
    供调试 CLI 展示与 P7 消融分析。
    """

    chunk_id: str
    text: str
    dense_score: float | None = None
    sparse_score: float | None = None
    fused_score: float | None = None
    rerank_score: float | None = None
    section_path: str = ""
    department: str = ""
    doc_type: str = ""
    source: str = ""
    page: int = 0
    seq: int = 0


class StageTiming(BaseModel):
    """单阶段耗时（P5 的 SSE step 事件数据源）。"""

    name: str
    ms: float


class RetrievalResult(BaseModel):
    """一次完整检索的输出：fused 为融合后重排前，final 为最终结果。"""

    query: str
    fused: list[RetrievedChunk] = Field(default_factory=list)
    final: list[RetrievedChunk] = Field(default_factory=list)
    timings: list[StageTiming] = Field(default_factory=list)
    recalled_dense: int = 0
    recalled_sparse: int = 0
