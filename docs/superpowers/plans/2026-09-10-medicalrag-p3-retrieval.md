# MedicalRAG P3 检索管线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现两阶段检索管线——dense（BGE-M3）+ BM25 双路并行召回 → 手写融合（RRF / 加权可切换）→ BGE-reranker 精排 → top-8 结果（含科室/文档类型过滤与全阶段耗时记录），配检索调试 CLI 与真实语料验证。

**Architecture:** 新模块 `backend/app/rag/`。融合函数为纯函数（RRF、min-max 归一化加权）；`HybridRetriever` 编排：查询向量化（复用 P1 EmbeddingProvider）→ 两路 Milvus 检索（pymilvus 同步 SDK，`asyncio.to_thread` 并行）→ 融合截断 → 重排（复用 P1 RerankerProvider，文本截断到 1000 字符仅用于打分）。**不用 Milvus 内置 hybrid_search/RRFRanker**——融合逻辑手写，为消融实验（RRF vs 加权）和面试可讲性服务。每阶段耗时记入 `RetrievalResult.timings`（P5 SSE step 事件的数据源）。

**Tech Stack:** 复用 P1/P2 全部设施（providers、Milvus `medical_chunks` 集合、1562 chunks 真实语料）；无新依赖。

**Spec:** `docs/superpowers/specs/2026-09-10-medicalrag-design.md` §4.1（两阶段检索）

## Global Constraints

- 沿用全部门禁：pytest 全绿 + ruff 0 错 + mypy 0 错；Conventional Commits
- 融合逻辑手写（这是设计决策，面试卖点）；Milvus 只做两路独立 search
- CI 无 Milvus：检索器单测用注入的 FakeClient/FakeProvider；真实链路在本机冒烟验证
- 检索接口是 P4 Agentic 编排的基础设施——输出结构（RetrievalResult）要能支撑后续每个节点的调用
- 默认参数：recall_k=50、rerank_k=30、top_k=8、rrf_k=60、dense_weight=sparse_weight=0.5

---

### Task 1: rag 模型与 RetrievalSettings

**Files:**
- Create: `backend/app/rag/__init__.py`、`backend/app/rag/models.py`
- Modify: `backend/app/core/config.py`（加 `RetrievalSettings` 与 `Settings.retrieval`）
- Test: `backend/tests/test_rag_models.py`

**Interfaces:**
- Produces:
  - `RetrievedChunk(BaseModel)`：`chunk_id: str`、`text: str`、`dense_score/sparse_score/fused_score/rerank_score: float | None = None`、`section_path/department/doc_type/source: str = ""`、`page: int = 0`、`seq: int = 0`
  - `StageTiming(BaseModel)`：`name: str`、`ms: float`
  - `RetrievalResult(BaseModel)`：`query: str`、`fused: list[RetrievedChunk]`（融合后重排前）、`final: list[RetrievedChunk]`（最终结果）、`timings: list[StageTiming]`、`recalled_dense/recalled_sparse: int = 0`
  - `RetrievalSettings(BaseModel)`：`recall_k=50, rerank_k=30, top_k=8, fusion="rrf", rrf_k=60, dense_weight=0.5, sparse_weight=0.5`；`Settings.retrieval: RetrievalSettings`

- [ ] 写 models.py / config 增量 → 测试（字段默认值、timings 追加）→ 门禁 → Commit `feat: rag 检索模型与配置`

### Task 2: 手写融合函数（RRF + 加权）

**Files:**
- Create: `backend/app/rag/fusion.py`
- Test: `backend/tests/test_fusion.py`

**Interfaces:**
- Produces:
  - `rrf_fuse(result_lists: list[list[RetrievedChunk]], k: int = 60) -> list[RetrievedChunk]`：`score = Σ 1/(k + rank + 1)`，跨列表去重合并（保留各自 dense/sparse_score，写 fused_score），按 fused_score 降序返回**新对象**（不修改输入）
  - `weighted_fuse(result_lists, weights: list[float]) -> list[RetrievedChunk]`：每列表内 min-max 归一化到 [0,1]（span=0 时记 1.0），`score = Σ w_i × norm_i`
  - 私有 `_own_score(chunk)`：取 dense_score 优先、sparse_score 兜底（每路结果的"自身分数"）

- [ ] TDD：先写测试（RRF 手算已知值验证、双列表重叠 chunk 合并、加权归一化正确性、空列表、输入不被修改）→ 实现 → 门禁 → Commit `feat: 手写 RRF 与加权融合`

RRF 已知值：chunk A 在列表1 rank0、列表2 rank1 → `1/61 + 1/62 ≈ 0.03252`。

### Task 3: HybridRetriever 双路召回 + 过滤

**Files:**
- Create: `backend/app/rag/retriever.py`
- Test: `backend/tests/test_retriever.py`

**Interfaces:**
- Consumes: `RetrievalSettings`、`EmbeddingProvider`、fusion 函数、Milvus `medical_chunks`
- Produces:
  - `HybridRetriever(*, client=None, embedder=None, reranker=None, settings=None)`（全部可注入）
  - `async retrieve(query: str, *, top_k: int | None, recall_k: int | None, fusion: str | None, department: str | None = None, doc_type: str | None = None, use_rerank: bool = True) -> RetrievalResult`
  - 内部：`_dense_search(vec, k, filt)` / `_sparse_search(query, k, filt)`（输出字段 `text/section_path/department/doc_type/source/page/seq`）；`_build_filter(department, doc_type)` → `"department == \"x\"" and ...`（值转义双引号）；两路 `asyncio.gather(asyncio.to_thread(...))` 并行
  - hit 转换：dense 路 distance→dense_score，sparse 路→sparse_score
  - 阶段耗时：embed_query / recall / fuse / rerank 四段记入 timings

- [ ] TDD：FakeClient（脚本化 search 结果）+ FakeEmbedder → 验证并行召回参数、filter 透传、融合调用、结果结构 → 门禁 → Commit `feat: HybridRetriever 双路混合召回`

### Task 4: 重排层

**Files:**
- Modify: `backend/app/rag/retriever.py`（`_rerank_chunks`）
- Test: `backend/tests/test_retriever.py`（追加）

**Interfaces:**
- Produces: `async _rerank_chunks(query, chunks, top_k)`：文本截断 `[:1000]` 打分 → 按 API 返回顺序（相关度降序）映射回 chunk、写 `rerank_score`、取 top_k；`use_rerank=False` 时直接 `fused[:top_k]`；融合结果先截断到 `rerank_k` 再送重排

- [ ] TDD：FakeReranker 返回指定顺序 → 验证重排改变顺序、top_k 截断、no_rerank 路径 → 门禁 → Commit `feat: BGE 重排层接入`

### Task 5: 检索调试 CLI

**Files:**
- Create: `backend/app/rag/__main__.py`
- Modify: `Makefile`（`retrieve` 目标）

**Interfaces:**
- CLI：`python -m app.rag --q "查询" [--fusion rrf|weighted] [--no-rerank] [--department X] [--doc-type Y] [--top-k N]`
  - 输出：各阶段耗时、召回数量、融合后 top10（fused_score）、最终结果（rerank_score）；stdout 强制 UTF-8（Windows）
- Makefile：`retrieve: cd backend && uv run python -m app.rag --q "$(q)"`

- [ ] 实现 → `make retrieve q="阿司匹林的禁忌"` 手工验证 → 门禁 → Commit `feat: 检索调试 CLI`

### Task 6: 真实语料端到端验证

- [ ] 对比实验（真实 Milvus + 真实 API，结果写入 `/tmp` 规避控制台编码）：
  - 同一查询跑 4 种配置：纯 dense（sparse 权重 0 的加权即视作纯 dense 对照）、rrf、rrf+rerank、weighted+rerank
  - 验证点：BM25 对精确术语（"HbA1c"、"SBP≥140"）的补充召回、重排对 top 命中率的提升、department 过滤生效
- [ ] README 勾选 P3 + 用法 → 全量门禁 → Commit `feat: P3 检索管线端到端验证`

## 依赖

```
T1 ─▶ T2 ─▶ T3 ─▶ T4 ─▶ T5 ─▶ T6
```
