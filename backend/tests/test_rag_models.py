from app.rag.models import RetrievalResult, RetrievedChunk, StageTiming


def test_retrieved_chunk_defaults():
    c = RetrievedChunk(chunk_id="abc-0001", text="高血压诊断标准")
    assert c.dense_score is None
    assert c.department == ""
    assert c.page == 0


def test_retrieval_result_holds_stages():
    r = RetrievalResult(query="q")
    r.timings.append(StageTiming(name="recall", ms=12.5))
    chunk = RetrievedChunk(chunk_id="a", text="t", fused_score=0.03)
    r.fused.append(chunk)
    r.final.append(chunk.model_copy(update={"rerank_score": 0.9}))
    assert r.timings[0].name == "recall"
    assert r.final[0].rerank_score == 0.9
    assert r.fused[0].rerank_score is None  # model_copy 不影响原对象
