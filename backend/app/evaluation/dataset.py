"""评估数据集：JSONL 加载与题目模型。"""

import json
from pathlib import Path

from pydantic import BaseModel, Field


class EvalQuestion(BaseModel):
    """一道评估题。ground_truth 为命中即得分的 chunk_id 集合（OOG/风险题为空）。"""

    id: str
    question: str
    ground_truth: list[str] = Field(default_factory=list)
    category: str = "in_kb"  # in_kb | multihop | out_of_kb | risk


def load_jsonl(path: Path) -> list[EvalQuestion]:
    questions = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            questions.append(EvalQuestion.model_validate(json.loads(line)))
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"{path.name}:{line_no} 解析失败: {exc}") from exc
    return questions


def load_datasets(root: Path) -> dict[str, list[EvalQuestion]]:
    """加载全部数据集：{"in_kb": [...], "multihop": [...], "out_of_kb": [...], "risk": [...]}。"""
    out: dict[str, list[EvalQuestion]] = {}
    for name in ("in_kb", "multihop", "out_of_kb", "risk"):
        path = root / f"{name}.jsonl"
        if path.exists():
            out[name] = load_jsonl(path)
    return out
