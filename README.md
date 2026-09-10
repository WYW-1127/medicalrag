# MedicalRAG —— 医学知识检索与问答 Copilot

生产级中文医学 RAG 系统：多格式知识入库 → Milvus 混合检索（dense + BM25 + RRF）+ BGE 重排 → LangGraph Agentic 编排（查询改写 / 多跳分解 / 检索反思 / 引用校验 / 安全拒答）→ 流式引用回答，配套量化评估体系与一键部署。

## 项目状态

- [x] P1 基础设施与骨架（FastAPI / 配置分层 / 模型抽象层 / MySQL+Redis+Milvus / CI）
- [x] P2 数据与 Ingestion 管线（多格式解析 / 结构感知分块 / Milvus 混合索引 / 幂等入库 CLI）
- [x] P3 检索管线（双路召回 + 手写 RRF/加权融合 + BGE 重排 + 属性过滤 + 调试 CLI）
- [x] P4 Agentic 编排与生成（LangGraph：分析/改写/分解/反思/引用生成/忠实度校验/拒答）
- [ ] P5 API 层（SSE / 认证 / 会话）
- [ ] P6 前端（对话 + 检索时间线 + 知识库管理）
- [ ] P7 评估体系（三层指标 + 消融实验）
- [ ] P8 部署打磨（一键全栈）

路线图：`docs/superpowers/plans/2026-09-10-medicalrag-roadmap.md`；设计文档：`docs/superpowers/specs/`

## 快速开始（P1：基础设施 + API 骨架）

前置：Docker Desktop、uv、Python 3.12（uv 可自动安装）

```bash
cp .env.example .env      # 填入 LLM__API_KEY / EMBEDDING__API_KEY / RERANKER__API_KEY
make install              # 安装后端依赖（uv sync）
make infra-up             # 启动 Milvus + MySQL + Redis（首次拉镜像约数分钟）
make check-infra          # 连通性检查，期望三行 [ok]
cd backend && cp ../.env.example .env && uv run alembic upgrade head   # 建表
cd backend && uv run uvicorn app.main:app --reload --port 8000         # 启动 API
```

访问 `http://127.0.0.1:8000/docs` 查看 OpenAPI；`/api/v1/health` 返回三依赖探活。

端口说明：宿主端口使用 3307（MySQL）/ 6380（Redis）/ 19530、9091（Milvus）/ 9002（minio 控制台），避开本机已有服务。

切换 LLM：编辑 `.env` 的 `LLM__BASE_URL / LLM__MODEL / LLM__API_KEY`（例如 GLM：
`https://open.bigmodel.cn/api/paas/v4` + `glm-4-flash`），无需改代码。

## 知识入库（P2）

```bash
make ingest-samples                  # 入库内置样例（指南 md / 药品说明书 json / 医学页面 html）
make probe q="高血压的诊断标准"        # 检索冒烟：dense 与 BM25 各返回 top-3
make ingest                          # 入库 data/raw/ 下的真实语料（放置规范见 data/raw/README.md）
cd backend && uv run python -m app.ingestion --dir ../data/raw --dry-run   # 只解析分块统计
```

管线能力：PDF（字号聚类标题 / 双栏 / 表格）/ Markdown / HTML / DOCX / JSON 药品说明书 / CSV；
结构感知分块（可配置 structural/fixed/recursive，供评估消融）；Milvus 混合索引
（dense HNSW-COSINE + BM25 jieba + 科室/文档类型元数据过滤）；按文档 hash 幂等重插。

## 检索管线（P3）

```bash
make retrieve q="HbA1c 控制目标"                                    # 完整链路：双路召回→RRF融合→BGE重排
cd backend && uv run python -m app.rag --q "妊娠期高血压如何用药" --department 心血管   # 科室过滤
cd backend && uv run python -m app.rag --q "哮喘" --fusion weighted --no-rerank         # 切融合策略/关重排
```

两阶段检索：dense（BGE-M3 语义）+ BM25（jieba 精确术语）各召回 top-50 → 手写融合
（RRF / 加权可切换，消融变量）→ BGE-reranker-v2-m3 精排取 top-8；每阶段耗时记录；
`RetrievalResult` 含 dense/sparse/fused/rerank 四级分数，可完整追溯排序变化。

## Agentic 问答（P4）

```bash
make ask q="血压多高算是高血压？需要吃药吗"   # 完整 Agentic 链路 + 引用 + 执行时间线
```

LangGraph 状态机（每节点独立 Pydantic schema，可单测）：

```
analyze（意图/风险）─┬─ 风险/闲聊 → 安全回复
                    └─ 医学 → rewrite（指代消解/术语化）→ decompose（多跳拆解）
                              → retrieve（子查询并行）→ grade（Self-RAG 反思，低置信带反馈重写 ≤2 轮）
                              → generate（引用角标）→ verify（逐句忠实度校验，失败再生成 ≤1 次）
                              → fallback（证据不足诚实拒答 + 免责声明）
```

## 目录结构

```
backend/     FastAPI 后端（app/core 配置与模型抽象层、app/models、alembic）
frontend/    React 前端（P6）
data/        原始与处理后语料（不入库）
evaluation/  测试集与评估报告
deploy/      docker-compose（基础设施）
scripts/     运维脚本
docs/        设计文档与 ADR
```
