# MedicalRAG 实施路线图

> 依据 spec：`docs/superpowers/specs/2026-09-10-medicalrag-design.md`
> 每个 Phase 一份独立计划（`docs/superpowers/plans/`），独立产出可运行、可测试的软件。上一阶段完成后再编写下一阶段的详细计划，保证计划基于实际代码。

| Phase | 计划文档 | 交付物（完成即验证） | 覆盖 spec 章节 |
|-------|----------|----------------------|----------------|
| P1 基础设施与骨架 | `2026-09-10-medicalrag-p1-foundation.md` | monorepo 骨架、FastAPI 应用工厂、配置分层、日志+trace-id、ModelProvider 抽象层（LLM/Embedding/Reranker）、SQLAlchemy 模型 + Alembic、/health 探活、Docker Compose（MySQL/Redis/Milvus）、CI、README 初版 | §2 架构、§7 工程化 |
| P2 数据与 Ingestion | （P1 完成后编写） | 多格式解析器（PDF/MD/HTML/DOCX/JSON）→ 统一文档树 → 结构感知分块 → Embedding → Milvus 写入（dense+BM25 sparse+元数据），`python -m app.ingest` CLI，幂等增量；首批真实数据入库 | §3 |
| P3 检索管线 | （P2 完成后编写） | Milvus hybrid search（RRF 融合，可配置）+ BGE reranker 精排 + 属性过滤；检索调试 CLI | §4.1 |
| P4 Agentic 编排与生成 | （P3 完成后编写） | LangGraph 状态机全部节点（analyze/rewrite/decompose/retrieve/grade/rerank/generate/verify/fallback）+ Redis checkpoint + 多轮指代消解 + 引用标注 | §4.2 |
| P5 API 层 | （P4 完成后编写） | JWT 认证、`POST /chat` SSE（token/step/done 事件）、会话历史、文档管理、ingest 触发；api 容器 | §5.1 |
| P6 前端 | （P5 完成后编写） | React 对话页（流式+引用浮窗）、检索过程时间线、知识库管理页、检索调试器；frontend 容器 | §5.2 |
| P7 评估体系 | （P6 完成后编写） | 100 题测试集、三层指标 CLI、LLM-as-Judge（中文 prompt）、消融实验矩阵与报告 | §6 |
| P8 部署打磨 | （P7 完成后编写） | 根目录 `docker compose up -d` 一键全栈、Makefile 完善、CI 补全、README 终版（架构图/截图/指标表）、ADR 决策记录 | §7 |
