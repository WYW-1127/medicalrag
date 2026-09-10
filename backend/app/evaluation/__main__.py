"""评估 CLI：python -m app.evaluation [--skip-agent] [--in-kb-agent N] [--k 5]

产出 evaluation/reports/<日期>-eval.md（消融矩阵 + 安全指标 + 抽样明细）。
"""

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path
from typing import Any

_stdout: Any = sys.stdout
if _stdout.encoding and _stdout.encoding.lower() != "utf-8":
    _stdout.reconfigure(encoding="utf-8")

from app.agents.graph import MedicalRAGAgent  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.core.providers.llm import LLMProvider  # noqa: E402
from app.evaluation.dataset import load_datasets  # noqa: E402
from app.evaluation.runner import run_agent_eval, run_retrieval_eval  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _fmt_f(x: float) -> str:
    return f"{x:.3f}"


def _build_report(
    retrieval: dict[str, dict[str, float]],
    agent_res: Any | None,
    k: int,
    counts: dict[str, int],
) -> str:
    lines = [
        f"# MedicalRAG 评估报告（{date.today().isoformat()}）",
        "",
        f"测试集规模：in-KB {counts.get('in_kb', 0)} / 多跳 {counts.get('multihop', 0)} / "
        f"知识库外 {counts.get('out_of_kb', 0)} / 风险 {counts.get('risk', 0)}",
        "",
        "## 一、检索层消融（in-KB + 多跳，纯计算指标）",
        "",
        f"| 配置 | Recall@{k} | MRR | nDCG@{k} |",
        "|------|-----------|-----|----------|",
    ]
    for name, m in retrieval.items():
        lines.append(
            f"| {name} | {_fmt_f(m[f'recall@{k}'])} | {_fmt_f(m['mrr'])} "
            f"| {_fmt_f(m[f'ndcg@{k}'])} |"
        )
    if agent_res is not None:
        lines += [
            "",
            "## 二、Agentic 全链路（生成层 + 安全层）",
            "",
            "| 指标 | 结果 | 说明 |",
            "|------|------|------|",
            f"| in-KB 正常回答率 | {_fmt_pct(agent_res.in_kb_answered_rate)} | 应接近 100% |",
            f"| 忠实度 | {_fmt_f(agent_res.faithfulness_avg)} | LLM 评审，1.0 满分 |",
            f"| 回答相关性 | {_fmt_f(agent_res.relevancy_avg)} | LLM-as-Judge，1.0 为满分 |",
            f"| 知识库外拒答率 | {_fmt_pct(agent_res.refusal_rate)} | 防幻觉，目标 ≥80% |",
            f"| 急症拦截率 | {_fmt_pct(agent_res.risk_intercept_rate)} | 医学安全，目标 100% |",
            "",
            "### 抽样明细（in-KB 子集）",
            "",
            "| 题目 | 路由 | 忠实度 | 相关性 | 引用数 |",
            "|------|------|--------|--------|--------|",
        ]
        for s in agent_res.samples[:15]:
            faith = "—" if s["faithfulness"] is None else _fmt_f(s["faithfulness"])
            relev = "—" if s["relevancy"] is None else _fmt_f(s["relevancy"])
            q_short = s["question"][:28]
            lines.append(
                f"| {q_short} | {s['route']} | {faith} | {relev} | {s['citations']} |"
            )
    lines += ["", "> 测试集由知识库反向生成（question generation）+ 手写安全集；",
              "> 生成层指标为中文自建 LLM-as-Judge（DeepSeek），评测代码见 app/evaluation/。"]
    return "\n".join(lines)


async def main() -> int:
    ap = argparse.ArgumentParser(prog="app.evaluation")
    ap.add_argument("--skip-agent", action="store_true", help="只跑检索层")
    ap.add_argument("--in-kb-agent", type=int, default=12, help="Agentic 层 in-KB 子集大小")
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()

    setup_logging()
    settings = get_settings()
    datasets = load_datasets(_REPO_ROOT / "evaluation" / "datasets")
    counts = {name: len(qs) for name, qs in datasets.items()}
    print(f"数据集: {counts}")

    in_kb = datasets.get("in_kb", [])
    multihop = datasets.get("multihop", [])
    oog = datasets.get("out_of_kb", [])
    risk = datasets.get("risk", [])

    retrieval_qs = [q for q in in_kb + multihop if q.ground_truth]
    print(f"\n== 检索层评估（{len(retrieval_qs)} 题 × 3 配置）==")
    retrieval = await run_retrieval_eval(retrieval_qs, settings, k=args.k)
    for name, m in retrieval.items():
        print(f"  {name}: {m}")

    agent_res = None
    if not args.skip_agent and in_kb:
        print(f"\n== Agentic 评估（in-KB 子集 {min(args.in_kb_agent, len(in_kb))} "
              f"+ OOG {len(oog)} + 风险 {len(risk)}）==")
        agent = MedicalRAGAgent(settings=settings)
        judge_llm = LLMProvider(settings.llm)
        agent_res = await run_agent_eval(
            in_kb[: args.in_kb_agent], oog, risk, agent, judge_llm
        )
        print(f"  in-KB 回答率: {agent_res.in_kb_answered_rate:.2%}")
        print(f"  忠实度: {agent_res.faithfulness_avg:.3f}  相关性: {agent_res.relevancy_avg:.3f}")
        print(f"  知识库外拒答率: {agent_res.refusal_rate:.2%}")
        print(f"  风险拦截率: {agent_res.risk_intercept_rate:.2%}")

    report_dir = _REPO_ROOT / "evaluation" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    out = report_dir / f"{date.today().isoformat()}-eval.md"
    out.write_text(
        _build_report(retrieval, agent_res, args.k, counts), encoding="utf-8"
    )
    print(f"\n报告已写入: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
