# MedicalRAG P7 评估体系 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 100 题测试集与三层指标评估：检索层（Recall@k/MRR/nDCG 纯计算）、生成层（中文 LLM-as-Judge：忠实度/回答相关性）、安全层（知识库外拒答率 + 急症安全拦截率），跑四配置消融矩阵产出 markdown 报告（简历量化数据来源）。

**Architecture:** 新模块 `backend/app/evaluation/`（metrics/judge/runner/CLI）+ `evaluation/datasets/*.jsonl`（版本化）+ `evaluation/reports/*.md`。**测试集构建方法**（面试点）：in-KB 题由知识库反向生成——从 Milvus 采样 chunk 作为 ground-truth，LLM 据此出题（question generation，标准合成评估技术）；多跳题取跨文档 chunk 对让 LLM 写对比问题；知识库外题与急症题手写。消融四配置：dense-only / hybrid(RRF) / hybrid+rerank / Agentic 全链路。为让 judge 拿到完整 chunk 文本，`AgentResult` 增加 `final_chunks` 字段。

**Tech Stack:** 复用 HybridRetriever（按配置构造不同 settings 实例）、MedicalRAGAgent、ask_json；无新依赖。

**Spec:** `docs/superpowers/specs/2026-09-10-medicalrag-design.md` §6

## Global Constraints

- 沿用全部门禁；指标/judge/runner 单测不碰真实服务（fakes）
- 数据集 JSONL 版本化入库；报告 markdown 入库（评估结果可追溯）
- judge 提示词中文、评分 0-1、输出 JSON（复用 ask_json 容错）
- 真实评估成本控制：检索层全量（~80 题 × 3 配置）；Agentic 层子集（in-KB 12 + OOG 20 + 风险 8 = 40 次 agent run）

---

### Task 1: 检索指标纯函数

**Files:** `app/evaluation/__init__.py`、`app/evaluation/metrics.py`、`tests/test_eval_metrics.py`

**Interfaces:**
- `recall_at_k(ranked_ids: list[str], gt: set[str], k: int) -> float`（|top-k∩gt|/|gt|，gt 空返回 0）
- `mrr(ranked_ids, gt) -> float`（首个命中的倒数排名，无命中 0）
- `ndcg_at_k(ranked_ids, gt, k) -> float`（二值相关性：DCG/IDCG）

### Task 2: 数据集 schema、loader 与手写集

**Files:** `app/evaluation/dataset.py`（`EvalQuestion: id/question/ground_truth: list[str]/category`；`load_jsonl(path)`）、`evaluation/datasets/out_of_kb.jsonl`（20 题手写：罕见病/知识库未覆盖主题）、`evaluation/datasets/risk.jsonl`（8 题手写急症/敏感）、`tests/test_eval_dataset.py`

### Task 3: LLM 测试集生成（真实运行）

**Files:** `scripts/build_eval_dataset.py`——按文档采样 chunk（in-KB 60：每文档按 chunk 占比分配，跳过表格/超短 chunk）→ LLM 出题（输出 {"question"}，题面要求"仅凭该资料可答、口语化、不照抄原句"）→ 写 `in_kb.jsonl`；多跳 20：同科室跨文档 chunk 对 → LLM 写对比/关联题 → `multihop.jsonl`（ground_truth=两 chunk）

- [ ] 真实生成 + 人工抽查 5 题 + 单测（loader/schema）

### Task 4: LLM-as-Judge

**Files:** `app/evaluation/judge.py`——`judge_faithfulness(llm, question, answer, contexts) -> JudgeScore(score, issues)`（每条关键陈述是否有资料支持，0-1）；`judge_relevancy(llm, question, answer) -> JudgeScore`（是否切题，0-1）；中文 prompts + ask_json。`tests/test_eval_judge.py`（ScriptedLLM）

### Task 5: 消融 runner 与 CLI

**Files:** `app/evaluation/runner.py`、`app/evaluation/__main__.py`、`app/agents/state.py`（AgentResult 加 `final_chunks: list[RetrievedChunk]`，graph.run 填充）、`tests/test_eval_runner.py`

**Interfaces:**
- `RETRIEVAL_CONFIGS: {"dense_only": {...}, "hybrid_rrf": {...}, "hybrid_rerank": {...}}`（dense_only 用 weighted+1/0 权重、no rerank；hybrid_rrf no rerank；hybrid_rerank rrf+rerank）
- `async run_retrieval_eval(questions, retriever_factory, k=5) -> dict[str, Metrics]`（每配置：Recall@5/MRR/nDCG@5）
- `async run_agent_eval(in_kb_subset, oog, risk, agent_factory) -> AgentMetrics(refusal_rate, risk_intercept_rate, faithfulness_avg, relevancy_avg, samples)`
- CLI：`python -m app.evaluation [--in-kb N] [--skip-agent]` → 输出 `evaluation/reports/YYYY-MM-DD-eval.md`（消融矩阵表 + 安全指标 + 抽样明细）

### Task 6: 真实评估与报告

- [ ] 生成数据集（若 T3 未完成）→ 跑检索层全量 + agent 层子集 → 报告落盘 → 数据核验（数字自洽：拒答率、召回率量级合理）

### Task 7: README 与收尾

- [ ] README 勾选 P7 + 指标表引用报告路径 → 全量门禁 → Commit

## 依赖

```
T1 ─▶ T5 ─▶ T6
T2 ─▶ T3 ─▶ T6
T4 ─▶ T5
```
