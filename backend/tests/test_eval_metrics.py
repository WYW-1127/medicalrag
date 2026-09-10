import pytest

from app.evaluation.metrics import mrr, ndcg_at_k, recall_at_k


def test_recall_at_k_basic():
    ranked = ["a", "b", "c", "d", "e"]
    assert recall_at_k(ranked, {"a"}, 5) == 1.0
    assert recall_at_k(ranked, {"e"}, 5) == 1.0
    assert recall_at_k(ranked, {"e"}, 3) == 0.0
    assert recall_at_k(ranked, {"a", "z"}, 5) == pytest.approx(0.5)
    assert recall_at_k(ranked, set(), 5) == 0.0


def test_mrr():
    assert mrr(["a", "b"], {"a"}) == pytest.approx(1.0)
    assert mrr(["a", "b"], {"b"}) == pytest.approx(0.5)
    assert mrr(["a", "b", "c", "d", "e"], {"e"}) == pytest.approx(0.2)
    assert mrr(["a", "b"], {"z"}) == 0.0


def test_ndcg():
    # 完美排序 = 1.0
    assert ndcg_at_k(["a", "b", "x"], {"a", "b"}, 3) == pytest.approx(1.0)
    # 全部命中但位次靠后 < 1.0
    assert ndcg_at_k(["x", "y", "a", "b"], {"a", "b"}, 4) < 1.0
    # 无命中
    assert ndcg_at_k(["x", "y"], {"a"}, 2) == 0.0
    # 单命中在 rank1 vs rank3
    high = ndcg_at_k(["a", "x", "y"], {"a"}, 3)
    low = ndcg_at_k(["x", "y", "a"], {"a"}, 3)
    assert high == pytest.approx(1.0) and 0 < low < high
    assert ndcg_at_k(["a"], set(), 1) == 0.0
