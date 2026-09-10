# MedicalRAG —— 医学知识检索与问答 Copilot 设计文档

- 日期：2026-09-10
- 状态：已确认（用户已批准全部 6 部分设计）
- 项目性质：生产级学习项目，目标为 AI Agent / AI Application Engineer 实习简历项目，需经得住技术面试

## 1. 项目定位与目标

构建一个面向中文医学知识的检索增强问答系统（RAG Copilot）。**不是** "PDF + 向量库 + LLM" 的 demo，而是一个具备以下特征的完整系统：

- 完整的离线数据管线：多格式解析 → 结构感知分块 → 混合索引
- 两阶段检索（混合召回 + 交叉编码器重排）与 Agentic 检索编排
- 基于量化指标的评估体系（含消融实验，简历数据来源）
- Docker Compose 一键部署、CI、可观测性等生产工程实践

**明确不做**（YAGNI）：知识图谱（GraphRAG）、Embedding 微调、云端部署与在线 Demo、多租户/权限体系、LangFuse（内存预算不足，用自建轻量 trace 替代）。

### 已确认的关键约束

| 维度 | 决策 |
|------|------|
| 数据源 | 中文医学指南/教材为主，多格式：PDF / Markdown / HTML / DOCX / JSON-CSV |
| 技术栈 | 后端 Python 3.12 + FastAPI；前端 React 18 + Vite + TypeScript |
| 时间预算 | 1-2 个月 |
| 模型接入 | 全部走云端 API（OpenAI 兼容抽象层）：LLM = DeepSeek/GLM 可切换；Embedding = BGE-M3（SiliconFlow）；Reranker = BGE-reranker-v2-m3（SiliconFlow） |
| 开发机限制 | 内存 <16GB，无本地重模型推理；本地服务总内存预算 ≤4GB |
| 核心亮点 | 混合检索 + 重排、Agentic RAG（LangGraph）、评估体系（三大必选方向） |
| 部署 | Docker Compose 一键启动 |

## 2. 系统架构

```
┌─────────┐ SSE  ┌───────────────────── Backend · FastAPI (async) ─────────────────────┐
│ Frontend │ ──▶ │  API 层 ──▶ LangGraph Agentic 编排 ──▶ 检索管线 ──▶ 生成(流式+引用) │
│ React+TS │ ◀── │                                                          │
└─────────┘      └──────┬──────────┬──────────────┬──────────────┬───────────────────┘
                        ▼          ▼              ▼              ▼
                    MySQL 8    Redis 7      Milvus 2.5      云端 API
                   (对话历史) (缓存/检查点)  (稠密+BM25混合)  (DeepSeek/GLM
                                                             +BGE Embed/Rerank)

┌─── Ingestion · 离线 CLI ────────────────────────────────────────────────┐
│ PDF/MD/HTML/DOCX/JSON ─▶ 格式适配器 ─▶ 统一文档树 ─▶ 结构感知分块        │
│      ─▶ Embedding API ─▶ Milvus 写入(dense+sparse+元数据) ─▶ 幂等增量   │
└────────────────────────────────────────────────────────────────────────┘
```

### 服务清单（Docker Compose，6 容器，总内存 ≤4GB）

| 容器 | 镜像 | 用途 |
|------|------|------|
| api | 自建（python:3.12-slim） | FastAPI 应用 |
| frontend | 自建（node build + nginx） | React 静态资源 + 反代 |
| milvus-standalone | milvusdb/milvus:v2.5.x | 混合检索（含 etcd、minio 两个伴生容器，不计入 6 容器主清单） |
| mysql | mysql:8 | 用户、会话、消息、ingestion 任务记录 |
| redis | redis:7 | 缓存、速率限制、LangGraph checkpoint |

### 关键架构决策（详见 docs/adr/，实施时逐条落地）

1. **只编排用 LangGraph，不整体依赖 LangChain**。LLM/Embedding/Reranker 调用通过自研 `ModelProvider` 抽象（openai SDK 直连，封装超时/重试/速率限制），检索融合与评估逻辑自研。理由：LangGraph 提供状态机编排与 checkpoint（简历关键词 + 实际价值），同时避免 LangChain 黑盒被面试追问击穿。
2. **模型抽象层 `ModelProvider`**：OpenAI 兼容接口 + Pydantic Settings 配置驱动，`.env` 一行切换 DeepSeek/GLM/Qwen。价值：成本控制、故障降级、评估时切换 judge 模型。
3. **Milvus 2.5 单库混合检索**（dense + 内置 BM25 sparse，RRF 融合），不用 Qdrant + Elasticsearch 双库。理由：<16GB 内存预算下双库过重；Milvus hybrid search 原生支持 RRF/加权融合，代码量小，把时间留给 Agentic 与评估。
4. **不引入 LangFuse**。用 loguru 结构化日志 + 请求级 trace-id + 每步耗时事件（喂给前端时间线）替代，预留 OpenTelemetry 接口。这是一次可讲的权衡决策。

## 3. 数据与 Ingestion 管线

### 3.1 数据源规划（全部公开可获取，存放于 `data/raw/`）

| 格式 | 内容 | 目录 |
|------|------|------|
| PDF | 临床诊疗指南（卫健委/中华医学会等公开渠道；心血管/内分泌/呼吸等常见科室），目标 20-50 份、2000-5000 页 | `data/raw/pdf/` |
| Markdown | 医学百科/诊疗笔记整理 | `data/raw/markdown/` |
| HTML | 权威医学网站指南页 | `data/raw/html/` |
| DOCX | 医院内部文档格式的示例资料 | `data/raw/docx/` |
| JSON/CSV | 药品说明书结构化数据、ICD 编码表（支撑剂量/禁忌/编码查询场景） | `data/raw/structured/` |

数据收集由项目实施阶段完成：优先公开指南 PDF；结构化药品数据从开源数据集获取；HTML 从权威医学站点页面导出。数据集仅本地学习用途，不入库分发。

### 3.2 Ingestion 管线（`python -m app.ingest` CLI，幂等、可增量）

1. **格式适配器**：每种格式一个 parser（PDF=PyMuPDF；MD=markdown 结构树；HTML=trafilatura；DOCX=python-docx；JSON/CSV=结构化转虚拟文档），统一输出 `Document → Section 层级树` 中间表示（Pydantic 定义）。
2. **PDF 解析重点**：文本提取 + 多栏检测（版面坐标启发式）+ 表格识别（医学指南的剂量表/适应证表转 Markdown 整块保留，不参与普通分块）。
3. **结构感知分块**：按标题层级切分，块目标 300-500 token（中文按字符近似），块携带完整 `section_path`；相邻块保留少量重叠上下文。分块策略做成可配置（strategy: structural | fixed | recursive），供评估消融。
4. **元数据 schema**：`doc_type`（guideline/drug_label/encyclopedia/...）、`department`（科室）、`source`（来源与 URL）、`section_path`、`page`、`chunk_hash`、`doc_hash`。
5. **Milvus collection 设计**：一个 collection 三类字段——dense 向量（BGE-M3，1024 维）、sparse（BM25 函数 + 中文 analyzer 全文索引）、标量元数据字段（含 `department`/`doc_type` 分区与过滤）。文档按 `doc_hash` 去重，重复入库走删除-重插，保证幂等。
6. **进度上报**：ingestion 作为后台任务运行，进度与统计（文档数/chunk 数/失败明细）写入 MySQL，前端知识库管理页可见。

## 4. 检索管线与 Agentic 编排

### 4.1 两阶段检索

1. **召回**：Milvus `hybrid_search`，dense 与 BM25 sparse 各取 top-50，RRF 融合（融合函数与参数可配置：rrf | weighted，供消融）。
2. **精排**：BGE-reranker-v2-m3 API 重排融合结果，取 top-8 进入生成上下文。

### 4.2 LangGraph 状态机

State（Pydantic）：`messages`、`query`、`intent`、`risk_flag`、`sub_queries`、`retrieved_chunks`、`grades`、`rewrite_feedback`、`iteration`、`answer`、`citations`、`verify_result`。

```
analyze_query ──▶ router
   ├─ 风险/闲聊分支 ───────────▶ 安全回复模板（急诊/自杀等风险 → 建议就医；闲聊 → 直接回答）
   └─ 医学问题分支 ─▶ rewrite（口语→医学术语、缩写展开；多轮场景做指代消解）
                       ─▶ decompose（对比/多跳问题拆子查询）
                       ─▶ retrieve（子查询并行 hybrid search）
                       ─▶ grade（LLM 对 chunk 相关性 0-1 打分；低置信 → 带 feedback 回 rewrite，最多 2 轮）
                       ─▶ rerank ─▶ generate（流式生成 + 引用角标）
                       ─▶ verify（逐句校验引用支持度；不通过 → 带反馈重新生成，最多 1 次）
                       ─▶ fallback（证据不足 → 明确拒答："现有知识库无法回答该问题" + 免责声明）
```

要点：
- 每个节点输入输出均有独立 Pydantic schema，可单测。
- 多轮对话：LangGraph checkpoint（Redis）持久化图状态；多轮查询先做指代消解再进入检索。
- 安全机制（医学场景必须）：风险检测前置、拒答兜底、答案尾部固定免责声明。

## 5. API 与前端

### 5.1 API（FastAPI，`/api/v1`，JWT 简单认证）

| 端点 | 说明 |
|------|------|
| `POST /chat` | SSE 流式。事件：`token`（增量文本）、`step`（Agentic 节点事件：节点名/耗时/中间结果摘要）、`done`（最终引用列表）、`error` |
| `GET /conversations`、`GET /conversations/{id}` | 会话与消息历史 |
| `GET /documents` | 知识库文档列表 + ingestion 状态 + chunk 预览 |
| `POST /admin/ingest` | 触发/查看 ingestion 后台任务 |
| `GET /health` | 健康检查（含 Milvus/MySQL/Redis/模型 API 探活） |

认证：JWT（演示级多用户，注册/登录），无复杂权限体系。

### 5.2 前端（React 18 + Vite + TS + Tailwind + shadcn/ui，医学蓝白主题）

- **对话页**：流式 markdown 渲染；引用角标 [1] hover 浮窗显示原文 chunk、来源文档、页码；顶部常驻免责声明。
- **检索过程时间线**（右侧面板）：实时展示每个 Agentic 节点轨迹——改写结果、检索与重排分数、grade 结论、重写原因、verify 结果。面试演示核心页面。
- **知识库管理页**：文档列表与解析/分块状态；检索调试器（输入 query，直接查看召回 + 重排结果与分数对比）。
- **会话管理**：多会话列表与切换。

## 6. 评估体系

### 6.1 测试集（~100 题，版本化于 `evaluation/datasets/`，JSONL）

- 60 题知识库内可答（人工出题 + 标注 ground-truth chunk）
- 20 题知识库外（考察拒答率，防幻觉核心指标）
- 20 题多跳/对比题（考察问题分解）

### 6.2 三层指标（`python -m app.evaluation` CLI，产出 markdown 报告 + 版本化结果）

1. **检索层**（纯计算，无 LLM）：Recall@k、MRR、nDCG
2. **生成层**（中文 prompt 自建 LLM-as-Judge，比 RAGAS 翻译更可控）：Faithfulness（引用忠实度）、Answer Relevancy、Citation Accuracy
3. **安全层**：知识库外拒答率、敏感问题安全回复率

### 6.3 消融实验矩阵（简历量化数据来源）

| 配置 | Recall@5 | Faithfulness | 拒答率 |
|------|----------|--------------|--------|
| 纯 dense | 待测 | 待测 | 待测 |
| + BM25 混合 | 待测 | 待测 | 待测 |
| + rerank | 待测 | 待测 | 待测 |
| + Agentic（完整） | 待测 | 待测 | 待测 |

附加消融：分块策略（fixed vs structural）、融合策略（RRF vs weighted）。

## 7. 部署与工程化

- **一键启动**：`docker compose up -d` 拉起全部服务；`make ingest` 灌数据；浏览器访问即用。提供 Makefile 常用命令。
- **依赖与质量**：uv + pyproject.toml；ruff（lint+format）；mypy（核心模块 strict）；pytest 单测（融合逻辑、状态机节点、API 集成）+ 评估冒烟。
- **CI**：GitHub Actions——lint → type-check → test，PR 门禁。
- **配置**：Pydantic Settings 分层（.env / .env.example），密钥零硬编码。
- **可观测**：loguru 结构化日志 + 请求 trace-id 贯穿全链路 + 每步耗时记录；预留 OpenTelemetry 接口。
- **文档**：README（架构图/快速启动/截图/指标表）+ `docs/adr/`（决策记录：为什么 Milvus、为什么混合检索、为什么 LangGraph、为什么不用 LangFuse）。

### 目录结构（monorepo）

```
medical-rag/
├── backend/
│   ├── app/
│   │   ├── api/          # 路由与 schema
│   │   ├── core/         # 配置、安全、日志、模型抽象层
│   │   ├── rag/          # 检索管线（召回/融合/重排）
│   │   ├── agents/       # LangGraph 状态机与节点
│   │   ├── ingestion/    # 解析/分块/入库
│   │   ├── evaluation/   # 评估框架与 judge
│   │   ├── models/       # MySQL ORM
│   │   └── services/     # 会话/文档/ingestion 服务
│   ├── tests/
│   └── pyproject.toml
├── frontend/             # React + Vite + TS
├── data/                 # raw/ 与 processed/
├── evaluation/           # datasets/ 与 reports/
├── deploy/               # docker-compose.yml 等
├── docs/                 # adr/ 与 specs/
└── README.md
```

## 8. 成功标准

1. `docker compose up -d` + `make ingest` 后，非开发者可在 10 分钟内得到可用系统
2. 评估报告显示完整消融矩阵，且混合检索相对纯 dense 在 Recall@5 上有可量化提升
3. 知识库外问题拒答率 ≥80%，引用忠实度（Faithfulness）≥85%
4. 前端检索时间线完整展示 Agentic 全过程
5. 任意核心模块（融合函数、状态机节点、分块器、judge prompt）在面试中被追问时，能对照代码讲清设计与权衡
