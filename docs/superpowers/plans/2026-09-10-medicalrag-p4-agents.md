# MedicalRAG P4 Agentic 编排与生成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 LangGraph 组装 Agentic 问答状态机——意图/风险分析 → 查询改写（指代消解+术语化）→ 多跳拆解 → 并行检索 → 检索反思（低置信带反馈重写，≤2 轮）→ 带引用生成 → 逐句忠实度校验（≤1 次再生成）→ 安全拒答兜底，输出带引用角标的回答与全流程步骤事件。

**Architecture:** 新模块 `backend/app/agents/`。每个节点是「输入 AgentState → 输出局部 State 更新」的函数，LLM 调用全部走可注入的 `LLMProvider`（结构化输出用「要求只输出 JSON + 容错解析（剥 code fence/降级重试）」）。图用 `langgraph.StateGraph` 组装，条件路由实现 Self-RAG 式反思循环。每个节点把 `StepEvent(name, ms, detail)` 追加进 state.steps——这是 P5 SSE 事件与前端检索时间线的数据源。检索节点复用 P3 `HybridRetriever`（子查询并行、按 chunk_id 去重合并）。**Redis checkpoint 留给 P5**（接线会话时加 checkpointer），P4 显式传 history。

**Tech Stack:** 新依赖 `langgraph`；复用 LLMProvider/ChatMessage/HybridRetriever/RetrievedChunk。

**Spec:** `docs/superpowers/specs/2026-09-10-medicalrag-design.md` §4.2

## Global Constraints

- 沿用全部门禁（pytest/ruff/mypy + Conventional Commits）
- CI 无真实服务：所有节点与整图路由用 FakeLLM/FakeRetriever 单测；真实链路本机冒烟
- 医学安全必须前置：风险查询（急诊/自杀/危重症状）不进检索直接安全回复；证据不足明确拒答；所有回答尾部免责声明
- 每个 LLM 节点的 prompt 是中文、角色明确、输出 schema 明确（面试素材，写在 `prompts.py` 集中管理）
- 反思上限：改写重试 ≤2、再生成 ≤1（防死循环，`AgentSettings` 可配）

---

### Task 1: AgentState / StepEvent / AgentSettings / 依赖

**Files:** `app/agents/__init__.py`、`app/agents/state.py`、`app/core/config.py`（增 AgentSettings）、`pyproject.toml`（增 langgraph）、`tests/test_agent_state.py`

**Interfaces:**
- `StepEvent(BaseModel)`: `name: str, ms: float, detail: str = ""`
- `AgentState(BaseModel)`（langgraph 图状态）: `query: str`、`history: list[ChatMessage] = []`、`analysis: QueryAnalysis | None`、`rewritten: str = ""`、`sub_queries: list[str] = []`、`feedback: str = ""`、`iteration: int = 0`、`chunks: list[RetrievedChunk] = []`、`grades: list[float] = []`、`answer: str = ""`、`citations: list[dict[str, Any]] = []`、`verify: VerifyResult | None`、`regen_count: int = 0`、`steps: list[StepEvent] = []`、`route: str = ""`（answered|safe|fallback）
- `QueryAnalysis(BaseModel)`: `intent: Literal["medical","chitchat","risk"]`、`risk_type: str = ""`、`reason: str = ""`
- `VerifyResult(BaseModel)`: `passed: bool`、`issues: list[str] = []`
- `AgentSettings(BaseModel)`: `max_rewrite_iterations=2, max_regenerate=1, grade_threshold=0.4, grade_min_relevant=2, subquery_max=3`；`Settings.agent`
- `AgentResult(BaseModel)`: `route: str, answer: str, citations: list[dict], steps: list[StepEvent], state: AgentState`（对 P5 的稳定出口）

### Task 2: analyze 与 safe_reply 节点 + JSON 工具

**Files:** `app/agents/prompts.py`、`app/agents/llm_io.py`、`app/agents/nodes/analyze.py`、`app/agents/nodes/safe_reply.py`、`app/agents/nodes/__init__.py`、`tests/test_node_analyze.py`

**Interfaces:**
- `llm_io.py`: `async ask_json(llm, system: str, user: str, schema: type[BaseModel]) -> BaseModel`——要求只输出 JSON、剥 ```json fence、解析失败把错误回传重试 1 次、再失败抛 `ProviderError`
- `ANALYZE_PROMPT`：分类 medical/chitchat/risk，risk 覆盖：胸痛/呼吸困难/大出血/意识障碍/自杀倾向/药物过量等危急情况；输出 `{"intent","risk_type","reason"}`
- `analyze_node(state) -> {"analysis", "steps"}`（异步，LLM 可注入）
- `safe_reply_node`：risk → 就医安全模板（立即拨打120/急诊，附风险类型）；chitchat → 通用简短回复；`route="safe"`，steps 记录
- 单测：FakeLLM 脚本化三种意图 + JSON 带 fence 的解析容错 + 解析失败重试

### Task 3: rewrite 与 decompose 节点

**Files:** `app/agents/nodes/rewrite.py`、`app/agents/nodes/decompose.py`、`tests/test_node_rewrite.py`

**Interfaces:**
- `REWRITE_PROMPT`：结合 history 做指代消解（"它的剂量呢"→"阿司匹林的剂量"）、口语→医学术语、缩写展开（心梗→心肌梗死）；有 feedback 时吸收失败原因调整改写；输出 `{"rewritten": str}`；`rewrite_node(state) -> {"rewritten","iteration(+1)","steps"}`
- `DECOMPOSE_PROMPT`：对比/多跳问题拆子查询（≤subquery_max），单一问题输出单元素数组；输出 `{"sub_queries": [str]}`；`decompose_node`
- 单测：指代消解（带 history）、feedback 传播、拆解数量上限截断、不拆解透传

### Task 4: retrieve 并行检索与 grade 反思节点

**Files:** `app/agents/nodes/retrieve.py`、`app/agents/nodes/grade.py`、`tests/test_node_retrieve.py`、`tests/test_node_grade.py`

**Interfaces:**
- `retrieve_node`（注入 HybridRetriever）：`asyncio.gather` 并行各子查询 `retrieve()`，按 chunk_id 去重合并（保留分数最高者），按 rerank/fused 分数排序取 `rerank_k`；steps 记录「N 路子查询 → M chunks」
- `GRADE_PROMPT`：编号 chunks 对 query 相关性 0-1 打分，输出 `{"scores": [float]}`；`grade_node` 写 `grades`
- 路由函数 `route_after_grade(state, settings) -> "generate"|"retry"|"fallback"`：有效相关数（≥grade_threshold）≥ grade_min_relevant → generate；不足且 iteration < max → retry（feedback=「最高分 X 仍低于阈值，请尝试更专业术语/拆解角度」）；迭代耗尽 → fallback
- 单测：FakeRetriever 并行合并去重；三路由分支；FakeLLM 分数解析

### Task 5: generate 引用生成 / verify 校验 / fallback 拒答

**Files:** `app/agents/nodes/generate.py`、`app/agents/nodes/verify.py`、`app/agents/nodes/fallback.py`、`tests/test_node_generate.py`

**Interfaces:**
- `GENERATE_PROMPT`：system=医学助手角色 + 只依据提供的编号资料回答 + 引用格式「陈述[编号]」+ 资料不足明确说无法回答（禁止编造）；context=编号 chunk（含来源/章节）；`generate_node` 生成后调用 `parse_citations(answer, chunks) -> (answer, citations)`：正则提取 `[n]`，citations 元素 `{"no": n, "chunk_id", "text", "source", "section_path", "page"}`；未标注引用的回答视为不合格 → verify issues
- `VERIFY_PROMPT`：给定回答与被引资料，逐句判断是否有原文支持，输出 `{"passed": bool, "issues": [str]}`；`verify_node`
- 路由 `route_after_verify`：passed → END（route=answered）；未过且 regen_count < max_regenerate → generate（system 追加 issues 反馈）；耗尽 → fallback
- `fallback_node`：固定拒答文案（「现有知识库无法可靠回答该问题…」+ 建议线下就医 + 免责声明），route=fallback
- 免责声明常量 `DISCLAIMER` 追加到 answered/fallback 回答尾部（safe 不加）
- 单测：引用角标解析与去重、verify 通过/失败/再生成路由、fallback 文案

### Task 6: 图组装 MedicalRAGAgent + 五路径单测

**Files:** `app/agents/graph.py`、`tests/test_graph.py`

**Interfaces:**
- `MedicalRAGAgent(llm=None, retriever=None, settings=None)`；`async run(query, history=None) -> AgentResult`
- 图结构（StateGraph + 条件边）：

```
START → analyze ─┬─(risk|chitchat)→ safe_reply → END
                 └─(medical)→ rewrite → decompose → retrieve → grade ─┬─generate→verify─┬─END
                                                                    ├─retry→rewrite    └─regen→generate
                                                                    └─fallback→END      └─fallback→END
```

- 五条路径单测（FakeLLM 按 call 次序脚本化 + FakeRetriever）：①medical happy path（引用回答）②risk 安全回复 ③grade 失败→重试→成功 ④verify 失败→再生成 ⑤迭代耗尽拒答；断言 route/answer 要点/steps 顺序

### Task 7: CLI + 真实链路冒烟

**Files:** `app/agents/__main__.py`、`Makefile`（`ask` 目标）、README 更新

- `python -m app.agents --q "..." [--history-json ...]`：打印回答、引用列表（来源/章节/页码）、步骤时间线
- 真实冒烟（DeepSeek + 真实检索）写入 /tmp 验证：普通医学问题（带引用）、对比型多跳问题（验证拆解）、知识库外问题（验证拒答）、风险问题（验证安全回复）
- Commit `feat: P4 Agentic 编排与生成`

## 依赖

```
T1 ─▶ T2 ─▶ T3 ─▶ T4 ─▶ T5 ─▶ T6 ─▶ T7
```
