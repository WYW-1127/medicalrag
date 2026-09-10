# MedicalRAG —— 医学知识检索与问答 Copilot

生产级中文医学 RAG 系统：多格式知识入库 → Milvus 混合检索（dense + BM25 + RRF）+ BGE 重排 → LangGraph Agentic 编排（查询改写 / 多跳分解 / 检索反思 / 引用校验 / 安全拒答）→ 流式引用回答，配套量化评估体系与一键部署。

## 项目状态

- [x] P1 基础设施与骨架（FastAPI / 配置分层 / 模型抽象层 / MySQL+Redis+Milvus / CI）
- [ ] P2 数据与 Ingestion 管线
- [ ] P3 检索管线（混合检索 + 重排）
- [ ] P4 Agentic 编排与生成（LangGraph）
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
