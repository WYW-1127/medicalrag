import pytest

from app.rag.fusion import rrf_fuse, weighted_fuse
from app.rag.models import RetrievedChunk


def _chunk(cid: str, text: str = "t", **scores: float) -> RetrievedChunk:
    return RetrievedChunk(chunk_id=cid, text=text, **scores)


def test_rrf_known_value():
    a1 = _chunk("A", dense_score=0.9)
    a2 = _chunk("A", sparse_score=5.0)  # A 在两路都排第一（各自列表 rank0）
    b1 = _chunk("B", dense_score=0.8)
    fused = rrf_fuse([[a1, b1], [a2]])
    by_id = {c.chunk_id: c for c in fused}
    assert by_id["A"].fused_score == pytest.approx(1 / 61 + 1 / 61)
    assert by_id["B"].fused_score == pytest.approx(1 / 62)
    assert fused[0].chunk_id == "A"  # 双路第一必须排最前


def test_rrf_dedup_merges_scores_and_preserves_text():
    a_dense = _chunk("A", "正文", dense_score=0.9)
    a_sparse = _chunk("A", "正文（应被丢弃，以首见为准）", sparse_score=5.0)
    fused = rrf_fuse([[a_dense], [a_sparse]])
    assert len(fused) == 1
    assert fused[0].dense_score == 0.9
    assert fused[0].sparse_score == 5.0
    assert fused[0].text == "正文"


def test_rrf_both_lists_rank_first_wins():
    a = _chunk("A", dense_score=0.9)
    b = _chunk("B", dense_score=0.1)
    fused = rrf_fuse([[a, b], []])
    assert [c.chunk_id for c in fused] == ["A", "B"]
    assert fused[0].fused_score > fused[1].fused_score


def test_rrf_does_not_mutate_input():
    a1 = _chunk("A", dense_score=0.9)
    a2 = _chunk("A", sparse_score=5.0)
    rrf_fuse([[a1], [a2]])
    assert a1.fused_score is None
    assert a2.fused_score is None


def test_weighted_normalizes_per_list():
    # 列表1（dense）：0.2..1.0 → A=1.0, B=0.0；列表2（sparse）：0..10 → B=1.0
    a_d, b_d = _chunk("A", dense_score=1.0), _chunk("B", dense_score=0.2)
    a_s, b_s = _chunk("A", sparse_score=0.0), _chunk("B", sparse_score=10.0)
    fused = weighted_fuse([[a_d, b_d], [a_s, b_s]], [0.5, 0.5])
    by_id = {c.chunk_id: c for c in fused}
    assert by_id["A"].fused_score == pytest.approx(0.5 * 1.0 + 0.5 * 0.0)
    assert by_id["B"].fused_score == pytest.approx(0.5 * 0.0 + 0.5 * 1.0)
    # 平分秋色时稳定排序即可
    assert len(fused) == 2


def test_weighted_single_list_span_zero():
    a = _chunk("A", dense_score=0.5)
    b = _chunk("B", dense_score=0.5)  # span=0 → 归一化记 1.0
    fused = weighted_fuse([[a, b]], [1.0])
    assert all(c.fused_score == pytest.approx(1.0) for c in fused)


def test_fusion_empty_inputs():
    assert rrf_fuse([[], []]) == []
    assert weighted_fuse([[], []], [0.5, 0.5]) == []
