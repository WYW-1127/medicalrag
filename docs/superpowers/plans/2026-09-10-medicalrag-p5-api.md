# MedicalRAG P5 API 层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 P4 的 Agent 变成产品化 HTTP 服务：JWT 认证、`POST /chat` SSE 流式（step/token/done/error 四类事件）、多轮会话 MySQL 持久化、知识库文档管理与后台 ingestion 触发、CORS。

**Architecture:** 认证用 bcrypt + python-jose（JWT），`get_current_user` FastAPI 依赖。流式核心：`token_sink: ContextVar` 让 generate 节点在 `chat_stream` 逐 token 回调；`MedicalRAGAgent.run_streaming` 基于 `graph.astream(stream_mode="values")` 每节点产出 step 事件，终态产出 AgentResult。SSE 端点用 asyncio.Queue 桥接（agent 生产者 task + StreamingResponse 异步生成器消费者）。新增 `Document` 表（ingestion 时同步写入，GET /documents 的数据源），alembic 迁移。会话历史作为 history 传入 agent（指代消解在 P4 已支持）。

**Tech Stack:** 复用全部 P1-P4；bcrypt/python-jose 已在依赖里；无新依赖。

**Spec:** `docs/superpowers/specs/2026-09-10-medicalrag-design.md` §5.1

## Global Constraints

- 沿用全部门禁；测试不碰真实 LLM/Milvus/MySQL（注入 fake；DB 测试用 aiosqlite）
- SSE 事件格式固定四类：`step`（StepEvent）、`token`（增量文本）、`done`（route/citations/conversation_id/message_id）、`error`（message）
- 认证范围：/auth 除外全部端点；演示级（无角色/权限体系）
- Agent 单例挂在 app.state（启动时构造一次，请求复用）

---

### Task 1: JWT 认证

**Files:** `app/core/security.py`（hash_password/verify_password/create_token/decode_token）、`app/api/deps.py`（get_current_user）、`app/api/routes/auth.py`（POST /auth/register、POST /auth/login）、`app/api/router.py` 挂载、`tests/test_auth.py`（aiosqlite session override + client）

**Interfaces:**
- `hash_password(p) -> str`、`verify_password(p, h) -> bool`、`create_access_token(username) -> str`、`decode_token(token) -> username | None`（过期/无效返回 None）
- `POST /api/v1/auth/register` `{username, password}` → 201 `{username}`；重名 409
- `POST /api/v1/auth/login` → `{access_token, token_type: "bearer"}`；错误 401
- `get_current_user`：`Authorization: Bearer <jwt>` → User 记录；无效 401。app.state.session_factory 可覆盖（测试注入 aiosqlite）
- 测试：注册→登录→带 token 访问受保护端点；错密码 401；无 token 401

### Task 2: Document 模型与 pipeline 写入

**Files:** `app/models/document.py`（Document: id, doc_hash unique, source, title, doc_type, department, chunk_count, created_at/updated_at）、`app/models/__init__.py`、alembic autogenerate 迁移、`app/ingestion/pipeline.py`（`_record_document(meta, chunk_count, title)`，与 _record_job 同样的降级策略）、`tests/test_document_model.py`

**Interfaces:**
- `Document` 表名 `documents`；pipeline upsert 成功后按 doc_hash 写入/更新（重复入库更新 chunk_count）
- 测试：模型字段；fake session 写入 roundtrip（aiosqlite）

### Task 3: 会话服务与端点

**Files:** `app/services/conversations.py`（create_conversation/get_user_conversations/get_conversation_messages/append_message/update_title）、`app/api/routes/conversations.py`、`tests/test_conversations.py`

**Interfaces:**
- `GET /api/v1/conversations` → 当前用户会话列表（id/title/created_at，倒序）
- `GET /api/v1/conversations/{id}/messages` → 消息列表（role/content/citations/latency_ms/created_at）；他人会话 404
- append_message 内部供 chat 使用（含 citations JSON、latency_ms）
- 测试：aiosqlite 全 CRUD + 权限隔离

### Task 4: Agent 流式化

**Files:** `app/agents/streaming.py`（`token_sink: ContextVar[Callable[[str], None] | None]`）、`app/agents/nodes/generate.py`（sink 存在时走 chat_stream）、`app/agents/graph.py`（`run_streaming` async generator：yield `("step", StepEvent)` … `("result", AgentResult)`）、`tests/test_agent_streaming.py`

**Interfaces:**
- `run_streaming(query, history=None) -> AsyncIterator[tuple[str, StepEvent | AgentResult | str]]`
- values 模式 astream；state.steps 增量 → step 事件；终态 → result 事件；token 通过 token_sink（API 层设置）
- generate：`sink = token_sink.get()`，非空则流式拼接 + 逐 token sink(t)
- 测试：FakeLLM 的 chat_stream 逐 token；断言 step 顺序、result.route、sink 收到全部 token；无 sink 时行为不变（run 旧路径回归）

### Task 5: POST /chat SSE

**Files:** `app/api/routes/chat.py`、`app/main.py`（app.state.agent + lifespan 构造、session 工厂）、`tests/test_chat_sse.py`

**Interfaces:**
- `POST /api/v1/chat` `{query: str, conversation_id?: int}`（认证）→ `text/event-stream`
- 事件序：`step`* / `token`*（仅生成阶段）/ `done`{route, answer?, citations, conversation_id, message_id} / `error`
- 行为：无 conversation_id 则创建（title=query 前 20 字）；加载最近 10 条历史传 agent；完成后 append user+assistant 消息（assistant 含 citations、总耗时）
- 实现：asyncio.Queue + 生产者 task（在 task 内 token_sink.set）；消费者转 `event: X\ndata: {...}\n\n`
- 测试：fake agent（app.state.agent 注入）验证事件序与持久化调用

### Task 6: documents/admin 端点 + CORS

**Files:** `app/api/routes/documents.py`、`app/api/routes/admin.py`、`app/main.py`（CORS allow localhost:5173）、`tests/test_documents_admin.py`

**Interfaces:**
- `GET /api/v1/documents` → documents 表列表 + 最近 IngestJob 状态
- `GET /api/v1/documents/{doc_hash}/chunks?k=3` → Milvus 按文档采样 chunk（注入 client）
- `POST /api/v1/admin/ingest` `{dir?}` → 后台 task 启动 run_ingestion，返回 `{started: true}`；`GET /api/v1/admin/ingest` → 最近 jobs
- CORS：allow_origins=["http://localhost:5173"]
- 测试：fake session/client

### Task 7: 真实 SSE 冒烟 + README

- uvicorn 启动 → curl 注册/登录 → curl -N SSE 聊天（真实 DeepSeek+检索）验证事件流完整 → 会话历史端点核对
- README 勾选 P5 + API 用法；全量门禁；Commit

## 依赖

```
T1 ─▶ T3 ─▶ T5 ─▶ T7
T2 ─────────↗   T6 ─▶ T7
T4 ─▶ T5
```
