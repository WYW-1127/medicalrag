# MedicalRAG P8 部署打磨 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 仓库根目录 `docker compose up -d` 一键拉起全栈（api + frontend + Milvus + MySQL + Redis + 伴生），CI 覆盖前后端，5 篇 ADR 决策记录，README 终版（架构图/截图/指标/一键启动）。

**Architecture:** 根目录 `docker-compose.yml` 整合全栈：复用 deploy/ 的 5 个基础设施服务定义（YAML anchor 或直接复制整合），新增 `api`（python3.12-slim + uv 构建，entrypoint 先 `alembic upgrade head` 再 uvicorn，依赖 mysql/milvus 健康）与 `frontend`（P6 已建镜像，nginx 反代 `api:8000`）。api 容器环境变量显式指向容器网络服务名（覆盖 .env 的 localhost 值），密钥经 `env_file: .env` 注入。数据入库保持 host 侧（`make ingest` 走端口映射）。

**Tech Stack:** uv 官方镜像（ghcr 镜像源走 daocloud 代理）、python:3.12-slim、已有 frontend nginx 镜像；无新代码依赖。

**Spec:** §7（部署与工程化）

## Global Constraints

- 沿用全部门禁；镜像源一律走国内可达源（daocloud/1ms.run，Dockerfile 内注释可切官方）
- api 容器不承担 ingestion（数据在 host，`make ingest` 走端口映射；admin 端点仅演示）
- 密钥不进镜像：compose `env_file: .env` + environment 显式覆盖连接串
- README 是简历门户：架构图 + 一键启动 + 截图 + 指标 + ADR 索引齐全

---

### Task 1: backend Dockerfile + .dockerignore
- 多阶段：`uv:python3.12` 装依赖 → `python:3.12-slim` 运行；entrypoint=`alembic upgrade head && uvicorn`
### Task 2: 根目录 docker-compose.yml 全栈
- services: etcd/minio/milvus/mysql/redis（同 deploy 版）+ api（8000，env 覆盖指向容器名）+ frontend（80→5182 映射避开已占端口）
- depends_on healthcheck；api healthcheck `/api/v1/health`
### Task 3: 构建 + 全栈启动验证
- docker build api/frontend → `docker compose up -d` → health 全绿 → 前端 http://localhost:5182 可访问且代理通
### Task 4: Makefile 完善
- `up/down/logs/build`（全栈）；保留原有目标
### Task 5: CI 加 frontend job
- npm ci + npm run build（tsc 检查含在内）
### Task 6: ADR ×5（docs/adr/）
- 0001 向量库选型 Milvus；0002 混合检索+重排（引消融数据）；0003 LangGraph 编排；0004 自建轻量 trace 而非 LangFuse；0005 评估方法（反向生成测试集+LLM-as-Judge）
### Task 7: README 终版 + 收尾
- 项目状态全勾、ASCII 架构图、一键启动、ADR 索引；全量门禁；最终 commit
