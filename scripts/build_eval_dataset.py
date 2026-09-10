"""从知识库反向生成评估测试集（question generation 标准技术）。

用法（仓库根目录）：
  cd backend && uv run python ../scripts/build_eval_dataset.py [--in-kb 60] [--multihop 20]

- in_kb：按文档 chunk 占比采样 → LLM 据每段资料出题（ground_truth=该 chunk）
- multihop：跨文档 chunk 对 → LLM 写对比/关联题（ground_truth=两个 chunk）
输出：evaluation/datasets/in_kb.jsonl、multihop.jsonl（覆盖写，可重跑）
"""

import argparse
import asyncio
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.agents.llm_io import ask_json  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.core.providers.llm import ChatMessage, LLMProvider  # noqa: E402
from pydantic import BaseModel  # noqa: E402

QGEN_SYSTEM = """\
你是医学问答系统的测试集生成器。根据给定的医学资料，写一个真实用户可能会问的问题。
要求：
1. 答案必须能仅凭这段资料回答（不依赖资料外的知识）
2. 口语化、自然，像真实患者/家属的问法
3. 不要照抄资料原句，问题要具体（包含关键实体如药名/指标/疾病名）
4. 不要出「资料里说了什么」这类元问题

只输出 JSON：{"question": "..."}"""

MULTIHOP_SYSTEM = """\
你是医学问答系统的测试集生成器。给定来自两份不同文档的资料，写一个对比型或关联型问题，
该问题需要综合两段资料才能完整回答（例如 A药与B药的用法对比、某疾病的诊断与用药）。
要求口语化自然、不照抄原句。

只输出 JSON：{"question": "..."}"""


class QuestionOut(BaseModel):
    question: str


def fetch_chunks() -> list[dict]:
    from pymilvus import MilvusClient

    s = get_settings()
    client = MilvusClient(uri=s.milvus_uri)
    client.load_collection(s.milvus_collection)
    return client.query(
        collection_name=s.milvus_collection,
        filter="",
        limit=2000,
        output_fields=["chunk_id", "doc_hash", "text", "department", "source", "seq"],
    )


def usable(c: dict) -> bool:
    """跳过表格块与过短块（出题质量差）。"""
    text = c["text"].strip()
    return len(text) >= 60 and not text.startswith("|")


def sample_in_kb(chunks: list[dict], total: int) -> list[dict]:
    by_doc: dict[str, list[dict]] = {}
    for c in chunks:
        by_doc.setdefault(c["doc_hash"], []).append(c)
    picks: list[dict] = []
    grand = len(chunks)
    for doc_chunks in by_doc.values():
        quota = max(2, round(total * len(doc_chunks) / grand))
        picks.extend(random.sample(doc_chunks, min(quota, len(doc_chunks))))
    return picks[:total]


def sample_multihop_pairs(chunks: list[dict], pairs: int) -> list[tuple[dict, dict]]:
    by_doc: dict[str, list[dict]] = {}
    for c in chunks:
        by_doc.setdefault(c["doc_hash"], []).append(c)
    docs = list(by_doc.keys())
    out = []
    attempts = 0
    while len(out) < pairs and attempts < pairs * 10:
        attempts += 1
        d1, d2 = random.sample(docs, 2)
        c1, c2 = random.choice(by_doc[d1]), random.choice(by_doc[d2])
        if usable(c1) and usable(c2):
            out.append((c1, c2))
    return out


async def gen_question(llm: LLMProvider, system: str, context: str) -> str:
    out = await ask_json(
        llm, system, f"资料：\n{context[:1200]}", QuestionOut, temperature=0.7
    )
    q = out.question.strip()
    if len(q) < 8:
        raise ValueError(f"生成问题过短: {q!r}")
    return q


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-kb", type=int, default=60)
    ap.add_argument("--multihop", type=int, default=20)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    random.seed(args.seed)

    setup_logging()
    datasets_dir = Path(__file__).resolve().parents[1] / "evaluation" / "datasets"
    datasets_dir.mkdir(parents=True, exist_ok=True)

    all_chunks = fetch_chunks()
    pool = [c for c in all_chunks if usable(c)]
    print(f"知识库共 {len(all_chunks)} chunks，可用 {len(pool)}")

    llm = LLMProvider(get_settings().llm)

    # in-KB
    rows: list[dict] = []
    picks = sample_in_kb(pool, args.in_kb)
    for i, c in enumerate(picks, 1):
        try:
            q = await gen_question(llm, QGEN_SYSTEM, c["text"])
            rows.append({
                "id": f"in-{i:03d}", "question": q,
                "ground_truth": [c["chunk_id"]], "category": "in_kb",
            })
            print(f"[{i}/{len(picks)}] {q}")
        except Exception as exc:  # noqa: BLE001 单题失败不中断
            print(f"[{i}] 失败: {exc}")
        time.sleep(0.2)
    _dump(datasets_dir / "in_kb.jsonl", rows)
    print(f"in_kb.jsonl 写入 {len(rows)} 题")

    # multihop
    mh_rows: list[dict] = []
    for i, (c1, c2) in enumerate(sample_multihop_pairs(pool, args.multihop), 1):
        try:
            q = await gen_question(
                llm, MULTIHOP_SYSTEM, f"【资料一（{c1['source']}）】\n{c1['text']}\n\n【资料二（{c2['source']}）】\n{c2['text']}"
            )
            mh_rows.append({
                "id": f"mh-{i:03d}", "question": q,
                "ground_truth": [c1["chunk_id"], c2["chunk_id"]], "category": "multihop",
            })
            print(f"[多跳 {i}] {q}")
        except Exception as exc:  # noqa: BLE001
            print(f"[多跳 {i}] 失败: {exc}")
        time.sleep(0.2)
    _dump(datasets_dir / "multihop.jsonl", mh_rows)
    print(f"multihop.jsonl 写入 {len(mh_rows)} 题")
    return 0


def _dump(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
