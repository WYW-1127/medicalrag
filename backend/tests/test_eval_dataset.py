import json
from pathlib import Path

import pytest

from app.evaluation.dataset import EvalQuestion, load_datasets, load_jsonl


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")


def test_load_jsonl(tmp_path: Path):
    f = tmp_path / "in_kb.jsonl"
    _write(f, [
        {"id": "q1", "question": "高血压诊断标准？",
         "ground_truth": ["abc-0001"], "category": "in_kb"},
        {"id": "q2", "question": "哮喘用药？", "ground_truth": ["x-01", "x-02"]},
    ])
    f.write_text(f.read_text(encoding="utf-8") + "\n\n", encoding="utf-8")  # 追加空行
    qs = load_jsonl(f)
    assert len(qs) == 2
    assert qs[0].ground_truth == ["abc-0001"]
    assert qs[1].category == "in_kb"  # 默认值


def test_load_jsonl_bad_line_raises(tmp_path: Path):
    f = tmp_path / "bad.jsonl"
    f.write_text('{"id": "1", "question": "x"}\nnot-json\n', encoding="utf-8")
    with pytest.raises(ValueError, match="bad.jsonl:2"):
        load_jsonl(f)


def test_load_datasets_skips_missing(tmp_path: Path):
    _write(tmp_path / "risk.jsonl", [{"id": "r1", "question": "胸痛", "category": "risk"}])
    ds = load_datasets(tmp_path)
    assert "risk" in ds and len(ds["risk"]) == 1
    assert "in_kb" not in ds  # 缺失文件跳过


def test_eval_question_model():
    q = EvalQuestion(id="q", question="？")
    assert q.ground_truth == [] and q.category == "in_kb"
