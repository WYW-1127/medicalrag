# MedicalRAG P6 前端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** React 对话前端：登录、多会话流式对话（SSE token 逐字渲染 + markdown）、引用角标 hover 浮窗、Agentic 检索时间线实时面板、知识库管理页；Docker 化（nginx 托管 + API 反代）。

**Architecture:** Vite + React 18 + TypeScript + Tailwind v4（`@tailwindcss/vite` 插件，零配置）。SSE 用 fetch + ReadableStream 解析（EventSource 不支持 POST/自定义 header）。状态用轻量 hooks（无 redux）。API 走 Vite dev 代理 `/api → localhost:8000`，生产 nginx 同路径反代——前端代码零环境区分。**与 spec 的一处偏差**：shadcn/ui 的脚手架是交互式 CLI，替换为手写 Tailwind 组件（Button/Input/Card 等，视觉等价、可讲性更好）。

**Tech Stack:** react、react-dom、react-router-dom、react-markdown + remark-gfm、tailwindcss v4；无其余运行时依赖。

**Spec:** `docs/superpowers/specs/2026-09-10-medicalrag-design.md` §5.2

## Global Constraints

- 医学蓝白主题（primary #0e7490 系）；顶部常驻免责声明条
- 后端联调地址统一 `/api`（dev 代理 / prod 反代），不硬编码 host
- 每个任务以 `npm run build`（tsc -b && vite build）通过为门禁；不设前端单测（测试重心在后端，浏览器真机验证代替）
- 组件文件 ≤250 行，超出即拆分

---

### Task 1: 脚手架与登录页

**Files:** `frontend/`（Vite 模板生成）、`vite.config.ts`（react + tailwind 插件 + `/api` 代理）、`src/index.css`（`@import "tailwindcss"` + 主题变量）、`src/main.tsx`、`src/App.tsx`（Router + 登录守卫）、`src/stores/auth.ts`（token 存取 hook）、`src/pages/LoginPage.tsx`、`src/components/ui.tsx`（Button/Input/Card 手写组件）

- [ ] `npm create vite@latest frontend -- --template react-ts` → 装依赖 + tailwind → 清模板 → 实现登录页（注册/登录切换，调 `/api/v1/auth/*`）→ build 通过

### Task 2: API client 与 SSE 解析器

**Files:** `src/api/client.ts`（带 token 的 fetch 封装、401 跳登录）、`src/api/sse.ts`（`streamChat(body, handlers)`：fetch POST + ReadableStream 逐块解析 `event:`/`data:` 帧，回调 onStep/onToken/onDone/onError）、`src/types.ts`

- [ ] 实现 + build 通过（SSE 解析器是纯函数，后端真实联调在 T7）

### Task 3: 对话页（会话侧栏 + 消息区 + 流式渲染）

**Files:** `src/pages/ChatPage.tsx`、`src/components/Sidebar.tsx`（会话列表/新建/切换）、`src/components/MessageList.tsx`（react-markdown 渲染、流式 token 拼接、步骤指示）、`src/components/Composer.tsx`（输入框）

- [ ] 发送 → step/token 事件驱动 UI（token 逐字追加，步骤 badge 顺序点亮）→ done 后刷新会话列表 → build 通过

### Task 4: 引用角标浮窗

**Files:** `src/components/CitationMark.tsx`（markdown 渲染层把 `[n]` 替换为角标组件：hover/点击浮窗显示 chunk 原文、来源文档、章节、页码）

- [ ] done 事件的 citations 挂到消息上；角标 hover 浮窗样式 → build 通过

### Task 5: 检索时间线面板

**Files:** `src/components/TimelinePanel.tsx`（右侧面板：实时追加节点事件——名称/耗时/detail，当前节点高亮、完成打勾）

- [ ] step 事件实时渲染 → build 通过

### Task 6: 知识库管理页

**Files:** `src/pages/KnowledgePage.tsx`（文档表格：标题/科室/类型/chunk 数/更新时间；行展开看 chunk 采样；「触发入库」按钮 + 最近任务状态）

- [ ] 对接 `/api/v1/documents`、`/admin/ingest` → build 通过

### Task 7: Docker 化与真实联调验证

**Files:** `frontend/Dockerfile`（node build → nginx alpine）、`frontend/nginx.conf`（SPA 路由 + `/api` 反代 `api:8000`）、`deploy/docker-compose.yml`（加 `frontend` 服务）、README 截图与用法

- [ ] 起 API + 前端 dev server → 浏览器真实走通：登录 → 提问 → 流式回答 + 时间线 + 引用浮窗 → 知识库页（用 browser-use 截图存 `docs/screenshots/`）→ docker build 验证 → README → Commit

## 依赖

```
T1 ─▶ T2 ─▶ T3 ─▶ T4 ─▶ T5 ─▶ T7
T1 ──────────────▶ T6 ─▶ T7
```
