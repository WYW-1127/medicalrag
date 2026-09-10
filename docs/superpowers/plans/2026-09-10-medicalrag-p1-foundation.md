# MedicalRAG P1 基础设施与骨架 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建 MedicalRAG 后端骨架与本地基础设施——FastAPI 应用工厂、配置分层、日志与 trace-id、模型抽象层（LLM/Embedding/Reranker）、数据库模型与迁移、健康探活、Docker Compose（MySQL/Redis/Milvus）、CI。

**Architecture:** monorepo 的 `backend/` 内构建 async FastAPI 应用，配置用 Pydantic Settings 分层驱动，所有模型调用走 OpenAI 兼容抽象层（云端 API，不在本地跑模型），本地基础设施（MySQL 8 / Redis 7 / Milvus 2.5 standalone）由 Docker Compose 提供。本阶段不含 api/frontend 容器（分别属于 P5/P8）。

**Tech Stack:** Python 3.12、uv、FastAPI、Pydantic v2、SQLAlchemy 2.0 async + Alembic、openai SDK、httpx + tenacity、loguru、pymilvus、redis-py asyncio、pytest + pytest-asyncio + respx、ruff + mypy、GitHub Actions。

**Spec:** `docs/superpowers/specs/2026-09-10-medicalrag-design.md`（本计划实现其 §2 架构与 §7 工程化的第一阶段）

## Global Constraints

- Python `>=3.12`；后端依赖统一由 `backend/pyproject.toml` + uv 管理
- 后端所有 IO 一律 async；FastAPI 应用通过工厂 `create_app()` 创建
- LLM/Embedding/Reranker 一律云端 API（OpenAI 兼容或 HTTP JSON），禁止本地模型推理
- 密钥只从环境变量 / `.env` 读取，仓库内零硬编码密钥；`.env` 不入库，`.env.example` 入库
- 本地基础设施总内存 ≤4GB（Milvus standalone + etcd + minio + MySQL + Redis）
- 代码质量门禁：`ruff check .` 0 错误、`mypy app` 0 错误、`pytest` 全绿，三者通过任务才算完成
- API 统一前缀 `/api/v1`
- 提交信息用 Conventional Commits（feat/fix/docs/chore/test）
- 开发环境：Windows + Git Bash + Docker Desktop；命令均在仓库根目录 `C:\Users\wangy\Desktop\项目\MedicalRAG —— 医学知识检索与问答 Copilot` 下执行（bash 引号包裹路径）
- monorepo 目录：`backend/` `frontend/` `data/` `evaluation/` `deploy/` `docs/` `scripts/`（本阶段创建除 `frontend/` 外的骨架）

---

### Task 1: Monorepo 骨架与 FastAPI 应用工厂

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/router.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_main.py`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `Makefile`

**Interfaces:**
- Consumes: 无（首个任务）
- Produces: `create_app() -> FastAPI`（app/main.py）；`api_router: APIRouter`（app/api/router.py，前缀 `/api/v1` 挂载）；conftest 的 `client` fixture（`httpx.AsyncClient`，后续所有 API 测试复用）

- [ ] **Step 1: 创建目录与包骨架**

```bash
mkdir -p backend/app/api backend/tests data/raw data/processed evaluation/datasets evaluation/reports deploy scripts docs/adr
touch backend/app/__init__.py backend/app/api/__init__.py backend/tests/__init__.py
```

- [ ] **Step 2: 写 `backend/pyproject.toml`**

```toml
[project]
name = "medical-rag-backend"
version = "0.1.0"
description = "MedicalRAG backend —— 医学知识检索与问答 Copilot"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "loguru>=0.7",
    "httpx>=0.27",
    "openai>=1.40",
    "tenacity>=8.3",
    "sqlalchemy[asyncio]>=2.0.30",
    "asyncmy>=0.2.9",
    "alembic>=1.13",
    "pymilvus>=2.5.3",
    "redis>=5.0",
    "python-jose[cryptography]>=3.3",
    "bcrypt>=4.1",
]

[dependency-groups]
dev = [
    "pytest>=8.2",
    "pytest-asyncio>=0.24",
    "aiosqlite>=0.20",
    "ruff>=0.5",
    "mypy>=1.10",
    "respx>=0.21",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "ASYNC", "S"]
ignore = ["S101"]

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["S106"]

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]

[[tool.mypy.overrides]]
module = ["pymilvus.*", "asyncmy.*", "alembic.*"]
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = "tests.*"
ignore_errors = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 3: 写 `backend/app/main.py`（应用工厂）**

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield

    app = FastAPI(title="MedicalRAG API", version="0.1.0", lifespan=lifespan)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
```

- [ ] **Step 4: 写 `backend/app/api/router.py`**

```python
from fastapi import APIRouter

api_router = APIRouter()


@api_router.get("/")
async def root() -> dict[str, str]:
    return {"app": "MedicalRAG", "version": "0.1.0"}
```

- [ ] **Step 5: 写测试 `backend/tests/conftest.py` 与 `backend/tests/test_main.py`**

```python
# conftest.py
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
```

```python
# test_main.py
async def test_root_returns_app_info(client):
    resp = await client.get("/api/v1/")
    assert resp.status_code == 200
    assert resp.json() == {"app": "MedicalRAG", "version": "0.1.0"}


async def test_openapi_docs_available(client):
    resp = await client.get("/docs")
    assert resp.status_code == 200
```

- [ ] **Step 6: 写 `.gitignore`**

```gitignore
# Python
__pycache__/
*.py[cod]
.venv/
.mypy_cache/
.ruff_cache/
.pytest_cache/
dist/
build/
*.egg-info/

# 环境与密钥
.env
.env.*
!.env.example

# 数据与产物（大文件不入库）
data/raw/
data/processed/
evaluation/reports/

# Node（前端阶段使用）
node_modules/

# IDE / OS
.idea/
.vscode/
.DS_Store
Thumbs.db
```

- [ ] **Step 7: 写 `.env.example`（Task 2 会补全配置结构，此处先放模型与连接默认值）**

```bash
# ===== LLM（默认 DeepSeek；切换 GLM 示例见 README）=====
LLM__BASE_URL=https://api.deepseek.com/v1
LLM__API_KEY=sk-your-deepseek-key
LLM__MODEL=deepseek-chat

# ===== Embedding（SiliconFlow，BGE-M3）=====
EMBEDDING__BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING__API_KEY=sk-your-siliconflow-key
EMBEDDING__MODEL=BAAI/bge-m3

# ===== Reranker（SiliconFlow，BGE-reranker-v2-m3）=====
RERANKER__BASE_URL=https://api.siliconflow.cn/v1
RERANKER__API_KEY=sk-your-siliconflow-key
RERANKER__MODEL=BAAI/bge-reranker-v2-m3

# ===== 基础设施 =====
DATABASE_URL=mysql+asyncmy://root:medicalrag@localhost:3306/medicalrag
REDIS_URL=redis://localhost:6379/0
MILVUS_URI=http://localhost:19530

# ===== 应用 =====
JWT_SECRET=please-change-me-in-.env
DEBUG=false
```

- [ ] **Step 8: 写 `Makefile`（根目录；命令用 tab 缩进）**

```makefile
.PHONY: install lint fmt typecheck test infra-up infra-down infra-logs check-infra

install:
	cd backend && uv sync

lint:
	cd backend && uv run ruff check .

fmt:
	cd backend && uv run ruff format .
	cd backend && uv run ruff check --fix .

typecheck:
	cd backend && uv run mypy app

test:
	cd backend && uv run pytest -v

infra-up:
	docker compose -f deploy/docker-compose.yml up -d

infra-down:
	docker compose -f deploy/docker-compose.yml down

infra-logs:
	docker compose -f deploy/docker-compose.yml logs -f

check-infra:
	cd backend && uv run python ../scripts/check_infra.py
```

（Makefile 每行 recipe 是独立 shell，`cd backend` 不会跨行残留。）

- [ ] **Step 9: 安装依赖并跑测试**

```bash
cd backend
uv python install 3.12   # 若本机无 3.12 则执行，有则跳过
uv sync
uv run pytest -v
```

Expected: `test_root_returns_app_info` 与 `test_openapi_docs_available` 两条 PASS。

- [ ] **Step 10: Commit**

```bash
cd "C:\Users\wangy\Desktop\项目\MedicalRAG —— 医学知识检索与问答 Copilot"
git add -A
git commit -m "feat: monorepo 骨架与 FastAPI 应用工厂"
```

---

### Task 2: 配置分层（Pydantic Settings）

**Files:**
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/core/config.py`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Consumes: 无
- Produces: `Settings`（含嵌套 `llm: LLMSettings`、`embedding: EmbeddingSettings`、`reranker: RerankerSettings`；字段见代码）；`get_settings() -> Settings`（lru_cache 单例，env 嵌套分隔符 `__`，如 `LLM__API_KEY`）。后续所有模块只通过 `get_settings()` 取配置。

- [ ] **Step 1: 写失败测试 `backend/tests/test_config.py`**

```python
from app.core.config import Settings


def test_settings_defaults() -> None:
    s = Settings(_env_file=None)
    assert s.llm.model == "deepseek-chat"
    assert s.llm.temperature == 0.3
    assert s.embedding.model == "BAAI/bge-m3"
    assert s.embedding.dimensions == 1024
    assert s.reranker.model == "BAAI/bge-reranker-v2-m3"
    assert s.api_prefix == "/api/v1"


def test_settings_env_override_nested() -> None:
    import os

    os.environ["LLM__API_KEY"] = "sk-test-123"
    os.environ["LLM__MODEL"] = "glm-4-flash"
    os.environ["LLM__BASE_URL"] = "https://open.bigmodel.cn/api/paas/v4"
    try:
        s = Settings(_env_file=None)
        assert s.llm.api_key == "sk-test-123"
        assert s.llm.model == "glm-4-flash"
        assert s.llm.base_url == "https://open.bigmodel.cn/api/paas/v4"
    finally:
        del os.environ["LLM__API_KEY"]
        del os.environ["LLM__MODEL"]
        del os.environ["LLM__BASE_URL"]
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && uv run pytest tests/test_config.py -v
```

Expected: FAIL，`ModuleNotFoundError: No module named 'app.core'`。

- [ ] **Step 3: 写 `backend/app/core/config.py`**

```python
from functools import lru_cache

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseModel):
    base_url: str = "https://api.deepseek.com/v1"
    api_key: str = ""
    model: str = "deepseek-chat"
    temperature: float = 0.3
    timeout: float = 60.0
    max_retries: int = 3


class EmbeddingSettings(BaseModel):
    base_url: str = "https://api.siliconflow.cn/v1"
    api_key: str = ""
    model: str = "BAAI/bge-m3"
    dimensions: int = 1024


class RerankerSettings(BaseModel):
    base_url: str = "https://api.siliconflow.cn/v1"
    api_key: str = ""
    model: str = "BAAI/bge-reranker-v2-m3"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_nested_delimiter="__", extra="ignore"
    )

    app_name: str = "MedicalRAG"
    debug: bool = False
    api_prefix: str = "/api/v1"
    jwt_secret: str = "change-me"
    jwt_expire_minutes: int = 60 * 24 * 7

    database_url: str = "mysql+asyncmy://root:medicalrag@localhost:3306/medicalrag"
    redis_url: str = "redis://localhost:6379/0"
    milvus_uri: str = "http://localhost:19530"

    llm: LLMSettings = LLMSettings()
    embedding: EmbeddingSettings = EmbeddingSettings()
    reranker: RerankerSettings = RerankerSettings()


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

同时创建空文件 `backend/app/core/__init__.py`。

- [ ] **Step 4: 运行确认通过**

```bash
cd backend && uv run pytest tests/test_config.py -v
```

Expected: 两条 PASS。

- [ ] **Step 5: 跑全量测试 + lint + mypy**

```bash
cd backend && uv run pytest -v && uv run ruff check . && uv run mypy app
```

Expected: 全部 PASS / 0 错误。

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: Pydantic Settings 配置分层与嵌套模型配置"
```

---

### Task 3: 结构化日志与 TraceID 中间件

**Files:**
- Create: `backend/app/core/logging.py`
- Create: `backend/app/core/middleware.py`
- Modify: `backend/app/main.py`（挂载中间件、启动时初始化日志）
- Test: `backend/tests/test_middleware.py`

**Interfaces:**
- Consumes: `get_settings()`（Task 2）
- Produces: `setup_logging(debug: bool) -> None`（app/core/logging.py）；`trace_id_var: ContextVar[str]` 与 `get_trace_id() -> str`、`TraceIDMiddleware`（app/core/middleware.py）。响应头 `X-Trace-Id`；日志行内嵌 trace_id。后续所有请求日志与 step 事件都会带上它。

- [ ] **Step 1: 写失败测试 `backend/tests/test_middleware.py`**

```python
async def test_trace_id_header_present(client):
    resp = await client.get("/api/v1/")
    assert resp.status_code == 200
    assert "x-trace-id" in resp.headers
    assert len(resp.headers["x-trace-id"]) == 12


async def test_trace_id_unique_per_request(client):
    r1 = await client.get("/api/v1/")
    r2 = await client.get("/api/v1/")
    assert r1.headers["x-trace-id"] != r2.headers["x-trace-id"]
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && uv run pytest tests/test_middleware.py -v
```

Expected: FAIL，`KeyError: 'x-trace-id'`（断言失败）。

- [ ] **Step 3: 写 `backend/app/core/logging.py`**

```python
import logging
import sys

from loguru import logger


class InterceptHandler(logging.Handler):
    """把 stdlib logging（uvicorn 等）重定向到 loguru。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = str(record.levelno)

        frame, depth = sys._getframe(6), 6  # noqa: SLF001
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(debug: bool = False) -> None:
    logger.remove()
    logger.configure(extra={"trace_id": "-"})
    logger.add(
        sys.stdout,
        level="DEBUG" if debug else "INFO",
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <7}</level> | "
            "{extra[trace_id]} | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - {message}"
        ),
    )
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
```

- [ ] **Step 4: 写 `backend/app/core/middleware.py`**

```python
import contextvars
import uuid

from fastapi import Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")


def get_trace_id() -> str:
    return trace_id_var.get()


class TraceIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        trace_id = uuid.uuid4().hex[:12]
        trace_id_var.set(trace_id)
        with logger.contextualize(trace_id=trace_id):
            logger.info("{} {}", request.method, request.url.path)
            response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response
```

- [ ] **Step 5: 修改 `backend/app/main.py` 挂载**

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.middleware import TraceIDMiddleware


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        setup_logging(debug=settings.debug)
        yield

    app = FastAPI(title="MedicalRAG API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(TraceIDMiddleware)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
```

注意：`setup_logging` 在 lifespan 启动阶段调用，而 ASGITransport 测试不触发 lifespan，所以测试路径上中间件必须不依赖日志已初始化——`logger.contextualize` 对未配置的默认 sink 也安全，无需额外处理。

- [ ] **Step 6: 运行确认通过**

```bash
cd backend && uv run pytest tests/test_middleware.py -v && uv run pytest -v
```

Expected: 全部 PASS。

- [ ] **Step 7: 手工验证日志格式（可选但建议）**

```bash
cd backend && uv run uvicorn app.main:app --port 8000
# 另开终端：curl -i http://127.0.0.1:8000/api/v1/
# 观察响应头 X-Trace-Id 与终端日志行中的 12 位 trace_id 一致
```

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "feat: loguru 结构化日志与 X-Trace-Id 中间件"
```

---

### Task 4: ModelProvider 抽象层（LLM / Embedding / Reranker）

**Files:**
- Create: `backend/app/core/providers/__init__.py`（工厂）
- Create: `backend/app/core/providers/llm.py`
- Create: `backend/app/core/providers/embedding.py`
- Create: `backend/app/core/providers/reranker.py`
- Test: `backend/tests/test_providers_llm.py`
- Test: `backend/tests/test_providers_embedding.py`
- Test: `backend/tests/test_providers_reranker.py`

**Interfaces:**
- Consumes: `LLMSettings` / `EmbeddingSettings` / `RerankerSettings`、`get_settings()`（Task 2）
- Produces:
  - `ChatMessage(BaseModel)`：`role: Literal["system","user","assistant"]`，`content: str`
  - `LLMProvider`：`async chat(messages: list[ChatMessage], *, temperature: float | None = None) -> str`；`async chat_stream(messages, *, temperature=None) -> AsyncIterator[str]`
  - `EmbeddingProvider`：`async embed(texts: list[str]) -> list[list[float]]`
  - `RerankResult(BaseModel)`：`index: int`，`score: float`；`RerankerProvider`：`async rerank(query: str, documents: list[str]) -> list[RerankResult]`（按返回顺序即相关度降序）
  - 工厂：`get_llm_provider() -> LLMProvider`、`get_embedding_provider() -> EmbeddingProvider`、`get_reranker_provider() -> RerankerProvider`（lru_cache）
  - 异常：`ProviderError`（llm.py 定义，空内容等业务性失败）、`RerankerError`（reranker.py）
  - 构造函数均接受可注入 client（`AsyncOpenAI` / `httpx.AsyncClient`），测试不真实外呼

- [ ] **Step 1: 写失败测试 `backend/tests/test_providers_llm.py`**

```python
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.core.config import LLMSettings
from app.core.providers.llm import ChatMessage, LLMProvider, ProviderError


def _make_provider(client: Any) -> LLMProvider:
    return LLMProvider(LLMSettings(api_key="sk-test"), client=client)


class _FakeMessage:
    def __init__(self, content: str | None) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str | None) -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str | None) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeStream:
    """按顺序 yield delta.content（"你"、"好"、None），None 应被 chat_stream 过滤。"""

    def __init__(self) -> None:
        self._contents: list[str | None] = ["你", "好", None]

    async def __aiter__(self) -> AsyncIterator[Any]:
        for content in self._contents:

            class _Delta:
                pass

            _Delta.content = content

            class _Chunk:
                choices = [type("C", (), {"delta": _Delta()})()]

            yield _Chunk


class FakeCompletions:
    async def create(self, **kwargs: Any) -> Any:
        if kwargs.get("stream"):
            return _FakeStream()
        return _FakeResponse("阿司匹林肠溶片，一次 100mg。")


class FakeChat:
    completions = FakeCompletions()


class FakeAsyncOpenAI:
    chat = FakeChat()


class EmptyCompletions:
    @staticmethod
    async def create(**kwargs: Any) -> Any:
        return _FakeResponse(None)


class EmptyAsyncOpenAI:
    class chat:  # noqa: N801
        completions = EmptyCompletions()


async def test_chat_returns_content() -> None:
    provider = _make_provider(FakeAsyncOpenAI())
    answer = await provider.chat([ChatMessage(role="user", content="阿司匹林剂量")])
    assert answer == "阿司匹林肠溶片，一次 100mg。"


async def test_chat_empty_content_raises() -> None:
    provider = _make_provider(EmptyAsyncOpenAI())
    with pytest.raises(ProviderError):
        await provider.chat([ChatMessage(role="user", content="x")])


async def test_chat_stream_yields_deltas() -> None:
    provider = _make_provider(FakeAsyncOpenAI())
    tokens = [t async for t in provider.chat_stream([ChatMessage(role="user", content="hi")])]
    assert tokens == ["你", "好"]
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && uv run pytest tests/test_providers_llm.py -v
```

Expected: FAIL，`ModuleNotFoundError: No module named 'app.core.providers'`。

- [ ] **Step 3: 写 `backend/app/core/providers/llm.py`**

```python
from collections.abc import AsyncIterator
from typing import Literal

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.core.config import LLMSettings


class ProviderError(Exception):
    """模型提供方业务性失败（空内容、异常响应等）。"""


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMProvider:
    """OpenAI 兼容 Chat 客户端。超时与网络重试由 openai SDK 内置（max_retries）。"""

    def __init__(self, settings: LLMSettings, client: AsyncOpenAI | None = None) -> None:
        self._settings = settings
        self._client = client or AsyncOpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key,
            timeout=settings.timeout,
            max_retries=settings.max_retries,
        )

    async def chat(
        self, messages: list[ChatMessage], *, temperature: float | None = None
    ) -> str:
        resp = await self._client.chat.completions.create(
            model=self._settings.model,
            messages=[m.model_dump() for m in messages],
            temperature=self._settings.temperature if temperature is None else temperature,
        )
        content = resp.choices[0].message.content
        if content is None:
            raise ProviderError("LLM 返回空内容")
        return content

    async def chat_stream(
        self, messages: list[ChatMessage], *, temperature: float | None = None
    ) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=self._settings.model,
            messages=[m.model_dump() for m in messages],
            temperature=self._settings.temperature if temperature is None else temperature,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
```

注意：fake client 的 `create` 接收 `**kwargs` 即可兼容两个调用点。

- [ ] **Step 4: 运行确认通过**

```bash
cd backend && uv run pytest tests/test_providers_llm.py -v
```

Expected: 3 条 PASS。

- [ ] **Step 5: 写失败测试 `backend/tests/test_providers_embedding.py`**

```python
from app.core.config import EmbeddingSettings
from app.core.providers.embedding import EmbeddingProvider


class _Item:
    def __init__(self, vector: list[float]) -> None:
        self.embedding = vector


class _Data:
    def __init__(self, vectors: list[list[float]]) -> None:
        self.data = [_Item(v) for v in vectors]


class FakeEmbeddings:
    def __init__(self) -> None:
        self.received_input: list[str] | None = None

    async def create(self, **kwargs):  # type: ignore[no-untyped-def]
        self.received_input = kwargs["input"]
        return _Data([[0.1, 0.2], [0.3, 0.4]])


class FakeAsyncOpenAI:
    def __init__(self, embeddings: FakeEmbeddings) -> None:
        self.embeddings = embeddings


async def test_embed_returns_vectors_in_order() -> None:
    fake = FakeEmbeddings()
    provider = EmbeddingProvider(EmbeddingSettings(api_key="sk-test"), client=FakeAsyncOpenAI(fake))  # type: ignore[arg-type]
    vectors = await provider.embed(["高血压指南", "糖尿病指南"])
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert fake.received_input == ["高血压指南", "糖尿病指南"]


async def test_embed_empty_input_short_circuits() -> None:
    fake = FakeEmbeddings()
    provider = EmbeddingProvider(EmbeddingSettings(api_key="sk-test"), client=FakeAsyncOpenAI(fake))  # type: ignore[arg-type]
    assert await provider.embed([]) == []
    assert fake.received_input is None
```

- [ ] **Step 6: 运行确认失败后写实现 `backend/app/core/providers/embedding.py`**

先运行（Expected: FAIL `ModuleNotFoundError`），再写：

```python
from openai import AsyncOpenAI

from app.core.config import EmbeddingSettings


class EmbeddingProvider:
    """OpenAI 兼容 /embeddings 端点（SiliconFlow BGE-M3）。"""

    def __init__(self, settings: EmbeddingSettings, client: AsyncOpenAI | None = None) -> None:
        self._settings = settings
        self._client = client or AsyncOpenAI(
            base_url=settings.base_url, api_key=settings.api_key, timeout=30.0, max_retries=3
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = await self._client.embeddings.create(
            model=self._settings.model, input=texts
        )
        return [item.embedding for item in resp.data]
```

运行 `uv run pytest tests/test_providers_embedding.py -v`，Expected: 2 条 PASS。

- [ ] **Step 7: 写失败测试 `backend/tests/test_providers_reranker.py`（httpx + respx 真实 HTTP mock）**

```python
import httpx
import pytest
import respx

from app.core.config import RerankerSettings
from app.core.providers.reranker import RerankerError, RerankerProvider, RerankResult

SETTINGS = RerankerSettings(api_key="sk-test")
URL = "https://api.siliconflow.cn/v1/rerank"


@respx.mock
async def test_rerank_maps_results_in_api_order() -> None:
    route = respx.post(URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.93},
                    {"index": 0, "relevance_score": 0.41},
                ]
            },
        )
    )
    provider = RerankerProvider(SETTINGS)
    results = await provider.rerank("阿司匹林 剂量", ["感冒灵说明书", "阿司匹林肠溶片说明书"])
    assert results == [RerankResult(index=1, score=0.93), RerankResult(index=0, score=0.41)]
    assert route.called
    body = route.calls.last.request.read().decode()
    assert "阿司匹林" in body


@respx.mock
async def test_rerank_empty_documents_no_call() -> None:
    provider = RerankerProvider(SETTINGS)
    assert await provider.rerank("q", []) == []


@respx.mock
async def test_rerank_http_error_raises() -> None:
    respx.post(URL).mock(return_value=httpx.Response(401, json={"error": "bad key"}))
    provider = RerankerProvider(SETTINGS)
    with pytest.raises(RerankerError):
        await provider.rerank("q", ["d1"])
```

- [ ] **Step 8: 运行确认失败后写实现 `backend/app/core/providers/reranker.py`**

先运行（Expected: FAIL `ModuleNotFoundError`），再写：

```python
import httpx
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import RerankerSettings


class RerankerError(Exception):
    """rerank API 不可恢复错误（非 2xx 或响应结构异常）。"""


class RerankResult(BaseModel):
    index: int
    score: float


class RerankerProvider:
    """SiliconFlow 风格 /rerank 端点（非 OpenAI 标准，走 httpx + tenacity 重试）。"""

    def __init__(self, settings: RerankerSettings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(
            base_url=settings.base_url,
            timeout=30.0,
            headers={"Authorization": f"Bearer {settings.api_key}"},
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError)),
        reraise=True,
    )
    async def rerank(self, query: str, documents: list[str]) -> list[RerankResult]:
        if not documents:
            return []
        resp = await self._client.post(
            "/rerank",
            json={"model": self._settings.model, "query": query, "documents": documents},
        )
        if resp.status_code != 200:
            raise RerankerError(f"rerank API 返回 {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        try:
            return [
                RerankResult(index=item["index"], score=item["relevance_score"])
                for item in data["results"]
            ]
        except (KeyError, TypeError) as exc:
            raise RerankerError(f"rerank 响应结构异常: {exc}") from exc
```

运行 `uv run pytest tests/test_providers_reranker.py -v`，Expected: 3 条 PASS。

- [ ] **Step 9: 写工厂 `backend/app/core/providers/__init__.py`**

```python
from functools import lru_cache

from app.core.config import get_settings
from app.core.providers.embedding import EmbeddingProvider
from app.core.providers.llm import LLMProvider
from app.core.providers.reranker import RerankerProvider


@lru_cache
def get_llm_provider() -> LLMProvider:
    return LLMProvider(get_settings().llm)


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    return EmbeddingProvider(get_settings().embedding)


@lru_cache
def get_reranker_provider() -> RerankerProvider:
    return RerankerProvider(get_settings().reranker)
```

- [ ] **Step 10: 全量质量门禁**

```bash
cd backend && uv run pytest -v && uv run ruff check . && uv run mypy app
```

Expected: 全 PASS / 0 错误。

- [ ] **Step 11: Commit**

```bash
git add -A && git commit -m "feat: ModelProvider 抽象层（LLM/Embedding/Reranker）与工厂"
```

---

### Task 5: 数据库模型与会话层（SQLAlchemy async）

**Files:**
- Create: `backend/app/models/__init__.py`（显式导出全部模型）
- Create: `backend/app/models/base.py`
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/conversation.py`
- Create: `backend/app/models/ingest_job.py`
- Create: `backend/app/core/db.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Consumes: `get_settings()`（Task 2）
- Produces:
  - `Base`（DeclarativeBase）与 `TimestampMixin`（app/models/base.py）
  - 模型：`User(username 唯一, password_hash)`；`Conversation(user_id FK users.id, title)`；`Message(conversation_id FK conversations.id, role: str, content: str, citations: JSON|None, latency_ms: int|None)`；`IngestJob(status: str, total_docs: int, processed_docs: int, total_chunks: int, error: str|None, stats: JSON|None)`——表名 `users` / `conversations` / `messages` / `ingest_jobs`
  - `get_engine(url: str) -> AsyncEngine`、`get_session_factory(url: str) -> async_sessionmaker[AsyncSession]`（按 url 缓存）、FastAPI 依赖 `async get_session() -> AsyncIterator[AsyncSession]`（app/core/db.py）
  - IngestJob 的 `status` 取值：`pending` / `running` / `completed` / `failed`（字符串约定，P2/P5 使用）

- [ ] **Step 1: 写失败测试 `backend/tests/test_models.py`**

```python
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Base, Conversation, IngestJob, Message, User


@pytest.fixture
async def session():  # type: ignore[no-untyped-def]
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def test_conversation_with_messages_roundtrip(session) -> None:  # type: ignore[no-untyped-def]
    user = User(username="alice", password_hash="hashed")
    session.add(user)
    await session.flush()

    conv = Conversation(user_id=user.id, title="高血压用药咨询")
    session.add(conv)
    await session.flush()

    session.add(Message(conversation_id=conv.id, role="user", content="阿司匹林每天吃多少？"))
    session.add(
        Message(
            conversation_id=conv.id,
            role="assistant",
            content="根据指南……",
            citations=[{"chunk_id": "c-1", "source": "冠心病指南", "page": 12}],
            latency_ms=1234,
        )
    )
    await session.commit()

    msgs = (
        (await session.execute(select(Message).where(Message.conversation_id == conv.id)))
        .scalars()
        .all()
    )
    assert len(msgs) == 2
    assert msgs[1].citations[0]["source"] == "冠心病指南"
    assert msgs[1].latency_ms == 1234


async def test_ingest_job_defaults(session) -> None:  # type: ignore[no-untyped-def]
    job = IngestJob(status="pending")
    session.add(job)
    await session.commit()
    stored = (await session.execute(select(IngestJob))).scalars().one()
    assert stored.status == "pending"
    assert stored.total_docs == 0
    assert stored.error is None
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && uv run pytest tests/test_models.py -v
```

Expected: FAIL，`ImportError: cannot import name 'Base'`。

- [ ] **Step 3: 写模型文件**

`backend/app/models/base.py`：

```python
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
```

`backend/app/models/user.py`：

```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
```

`backend/app/models/conversation.py`：

```python
from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="新对话")


class Message(Base, TimestampMixin):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(nullable=True)
```

`backend/app/models/ingest_job.py`：

```python
from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class IngestJob(Base, TimestampMixin):
    __tablename__ = "ingest_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    total_docs: Mapped[int] = mapped_column(default=0)
    processed_docs: Mapped[int] = mapped_column(default=0)
    total_chunks: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

`backend/app/models/__init__.py`：

```python
from app.models.base import Base, TimestampMixin
from app.models.conversation import Conversation, Message
from app.models.ingest_job import IngestJob
from app.models.user import User

__all__ = ["Base", "TimestampMixin", "Conversation", "IngestJob", "Message", "User"]
```

- [ ] **Step 4: 写 `backend/app/core/db.py`**

```python
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engines: dict[str, AsyncEngine] = {}
_session_factories: dict[str, async_sessionmaker[AsyncSession]] = {}


def get_engine(url: str) -> AsyncEngine:
    if url not in _engines:
        _engines[url] = create_async_engine(url, pool_pre_ping=True)
    return _engines[url]


def get_session_factory(url: str) -> async_sessionmaker[AsyncSession]:
    if url not in _session_factories:
        _session_factories[url] = async_sessionmaker(
            get_engine(url), expire_on_commit=False
        )
    return _session_factories[url]


async def get_session() -> AsyncIterator[AsyncSession]:
    from app.core.config import get_settings

    factory = get_session_factory(get_settings().database_url)
    async with factory() as session:
        yield session
```

- [ ] **Step 5: 运行确认通过 + 全量门禁**

```bash
cd backend && uv run pytest -v && uv run ruff check . && uv run mypy app
```

Expected: 全 PASS / 0 错误。

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: SQLAlchemy async 模型（用户/会话/消息/入库任务）与会话层"
```

---

### Task 6: /health 健康探活端点

**Files:**
- Create: `backend/app/api/routes/__init__.py`
- Create: `backend/app/api/routes/health.py`
- Modify: `backend/app/api/router.py`
- Test: `backend/tests/test_health.py`

**Interfaces:**
- Consumes: `get_settings()`、`get_engine()`（Task 2/5）；pymilvus `MilvusClient`、redis-py asyncio
- Produces: `GET /api/v1/health` 响应 `{"status": "ok"|"degraded", "checks": {"mysql": "ok"|"unreachable", "redis": ..., "milvus": ...}}`，HTTP 恒 200（degraded 也是 200，供前端与 compose 健康检查区分使用）；模块级检查函数 `check_mysql() -> bool`、`check_redis() -> bool`、`check_milvus() -> bool`（可被测试 monkeypatch）

- [ ] **Step 1: 写失败测试 `backend/tests/test_health.py`**

```python
from httpx import AsyncClient

from app.api.routes import health as health_module


async def _ok() -> bool:
    return True


async def test_health_all_up(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(health_module, "check_mysql", _ok)
    monkeypatch.setattr(health_module, "check_redis", _ok)
    monkeypatch.setattr(health_module, "check_milvus", lambda: True)
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "ok",
        "checks": {"mysql": "ok", "redis": "ok", "milvus": "ok"},
    }


async def test_health_degraded_when_one_down(client: AsyncClient, monkeypatch) -> None:
    async def _fail() -> bool:
        return False

    monkeypatch.setattr(health_module, "check_mysql", _ok)
    monkeypatch.setattr(health_module, "check_redis", _fail)
    monkeypatch.setattr(health_module, "check_milvus", lambda: True)
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "degraded"
    assert resp.json()["checks"]["redis"] == "unreachable"
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && uv run pytest tests/test_health.py -v
```

Expected: FAIL，`ModuleNotFoundError` 或 404。

- [ ] **Step 3: 写 `backend/app/api/routes/health.py`**

```python
import asyncio

from fastapi import APIRouter
from pymilvus import MilvusClient
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import get_engine

router = APIRouter(tags=["health"])


async def check_mysql() -> bool:
    try:
        engine = get_engine(get_settings().database_url)
        async with asyncio.timeout(3), engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def check_redis() -> bool:
    try:
        client = Redis.from_url(get_settings().redis_url)
        async with asyncio.timeout(3):
            await client.ping()
        await client.aclose()
        return True
    except Exception:
        return False


def check_milvus() -> bool:
    """pymilvus 是同步 SDK，由路由层放到线程池执行。"""
    try:
        client = MilvusClient(uri=get_settings().milvus_uri)
        client.get_server_version()
        client.close()
        return True
    except Exception:
        return False


@router.get("/health")
async def health() -> dict[str, object]:
    checks: dict[str, bool] = {
        "mysql": await check_mysql(),
        "redis": await check_redis(),
        "milvus": await asyncio.to_thread(check_milvus),
    }
    status = "ok" if all(checks.values()) else "degraded"
    return {
        "status": status,
        "checks": {name: "ok" if ok else "unreachable" for name, ok in checks.items()},
    }
```

- [ ] **Step 4: 修改 `backend/app/api/router.py` 挂载**

```python
from fastapi import APIRouter

from app.api.routes import health

api_router = APIRouter()
api_router.include_router(health.router)


@api_router.get("/")
async def root() -> dict[str, str]:
    return {"app": "MedicalRAG", "version": "0.1.0"}
```

- [ ] **Step 5: 运行确认通过 + 全量门禁**

```bash
cd backend && uv run pytest -v && uv run ruff check . && uv run mypy app
```

Expected: 全 PASS / 0 错误。

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: /health 端点（MySQL/Redis/Milvus 探活，降级状态）"
```

---

### Task 7: Docker Compose 基础设施与连通性脚本

**Files:**
- Create: `deploy/docker-compose.yml`
- Create: `scripts/check_infra.py`
- Modify: 无（Makefile 的 infra-* / check-infra 目标 Task 1 已就位）

**Interfaces:**
- Consumes: `get_settings()`、`get_engine()`（Task 2/5）
- Produces: `deploy/docker-compose.yml`（服务：`etcd`、`minio`、`milvus`、`mysql`、`redis`；容器名前缀 `medicalrag-`；数据卷 `etcd_data` `minio_data` `milvus_data` `mysql_data`）；`scripts/check_infra.py`（三项连通全通过退出码 0，否则 1）。端口：MySQL 3306、Redis 6379、Milvus 19530/9091、minio 控制台 9001。默认凭据与 `.env.example` 一致（MySQL root/medicalrag，库 medicalrag）。

- [ ] **Step 1: 写 `deploy/docker-compose.yml`**

```yaml
# MedicalRAG 本地基础设施（P1）。
# 内存预算：etcd ~50MB + minio ~200MB + milvus ~2GB + mysql ~400MB + redis ~50MB ≈ 2.7GB
services:
  etcd:
    container_name: medicalrag-etcd
    image: quay.io/coreos/etcd:v3.5.14
    environment:
      - ETCD_AUTO_COMPACTION_MODE=revision
      - ETCD_AUTO_COMPACTION_RETENTION=1000
      - ETCD_QUOTA_BACKEND_BYTES=4294967296
      - ETCD_SNAPSHOT_COUNT=50000
    volumes:
      - etcd_data:/etcd
    command: etcd -advertise-client-urls=http://etcd:2379 -listen-client-urls http://0.0.0.0:2379 --data-dir /etcd
    healthcheck:
      test: ["CMD", "etcdctl", "endpoint", "health"]
      interval: 30s
      timeout: 20s
      retries: 3
    restart: unless-stopped

  minio:
    container_name: medicalrag-minio
    image: minio/minio:RELEASE.2024-05-28T17-19-04Z
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - minio_data:/minio_data
    command: minio server /minio_data --console-address ":9001"
    ports:
      - "9001:9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3
    restart: unless-stopped

  milvus:
    container_name: medicalrag-milvus
    image: milvusdb/milvus:v2.5.4
    command: ["milvus", "run", "standalone"]
    security_opt:
      - seccomp:unconfined
    environment:
      ETCD_ENDPOINTS: etcd:2379
      MINIO_ADDRESS: minio:9000
    volumes:
      - milvus_data:/var/lib/milvus
    ports:
      - "19530:19530"
      - "9091:9091"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9091/healthz"]
      interval: 30s
      start_period: 90s
      timeout: 20s
      retries: 5
    depends_on:
      - etcd
      - minio
    restart: unless-stopped

  mysql:
    container_name: medicalrag-mysql
    image: mysql:8.4
    environment:
      MYSQL_ROOT_PASSWORD: medicalrag
      MYSQL_DATABASE: medicalrag
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-uroot", "-pmedicalrag"]
      interval: 5s
      timeout: 5s
      retries: 20
    restart: unless-stopped

  redis:
    container_name: medicalrag-redis
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 20
    restart: unless-stopped

volumes:
  etcd_data:
  minio_data:
  milvus_data:
  mysql_data:
  redis_data:
```

- [ ] **Step 2: 写 `scripts/check_infra.py`**

```python
"""基础设施连通性检查：MySQL / Redis / Milvus。全部就绪退出码 0，否则 1。

用法（仓库根目录）：make check-infra
依赖 backend 虚拟环境（uv run 提供包）；脚本自身把 backend/ 加进 sys.path。
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402


async def main() -> int:
    settings = get_settings()
    ok = True

    try:
        from sqlalchemy import text

        from app.core.db import get_engine

        engine = get_engine(settings.database_url)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        print("[ok]   mysql")
    except Exception as exc:
        ok = False
        print(f"[fail] mysql: {exc}")

    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.redis_url)
        await client.ping()
        await client.aclose()
        print("[ok]   redis")
    except Exception as exc:
        ok = False
        print(f"[fail] redis: {exc}")

    try:
        from pymilvus import MilvusClient

        client = MilvusClient(uri=settings.milvus_uri)
        client.get_server_version()
        client.close()
        print("[ok]   milvus")
    except Exception as exc:
        ok = False
        print(f"[fail] milvus: {exc}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 3: 启动基础设施（首次拉镜像较慢，Milvus 就绪需 1-2 分钟）**

```bash
make infra-up
docker compose -f deploy/docker-compose.yml ps
```

Expected: 5 个服务状态全部 `Up (healthy)`（milvus 的 healthcheck 有 start_period 90s，耐心等待）。

- [ ] **Step 4: 连通性验证**

```bash
make check-infra
```

Expected: 三行 `[ok]`，退出码 0。

- [ ] **Step 5: 验证 /health 真实探活（可选）**

```bash
cd backend && uv run uvicorn app.main:app --port 8000
# 另开终端：curl http://127.0.0.1:8000/api/v1/health
# Expected: {"status":"ok","checks":{"mysql":"ok","redis":"ok","milvus":"ok"}}
```

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: Docker Compose 基础设施（Milvus/MySQL/Redis）与连通性脚本"
```

---

### Task 8: Alembic 异步迁移与首版 schema 上库

**Files:**
- Create: `backend/alembic.ini`、`backend/alembic/env.py`、`backend/alembic/script.py.mako`、`backend/alembic/versions/<generated>.py`（由 alembic init + autogenerate 生成）
- Modify: 无（生成后小改 env.py，见 Step 2）

**Interfaces:**
- Consumes: `Settings.database_url`、`Base.metadata` 与全部模型（Task 5）；MySQL 容器（Task 7）
- Produces: 迁移链（首个 revision），命令 `uv run alembic upgrade head`；P2+ 所有 schema 变更都走 alembic revision

- [ ] **Step 1: 初始化 alembic（async 模板）**

```bash
cd backend && uv run alembic init -t async alembic
```

Expected: 生成 `alembic.ini` 与 `alembic/` 目录。

- [ ] **Step 2: 编辑 `backend/alembic.ini` 与 `backend/alembic/env.py`**

`alembic.ini`：注释掉或删除 `sqlalchemy.url = ...` 行（url 由 env.py 从 Settings 注入，避免密钥/环境硬编码）。

`env.py` 整体替换为：

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.models import Base  # noqa: F401  导入即注册全部模型

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: 生成首版迁移**

前置：`make infra-up` 且 mysql healthy；根目录 `backend/` 下有 `.env`（可先 `cp ../.env.example .env`，模型 key 可留空，本任务不外呼）。

```bash
cd backend
cp ../.env.example .env
uv run alembic revision --autogenerate -m "init tables: users conversations messages ingest_jobs"
```

Expected: `alembic/versions/` 下生成新文件，其中 `op.create_table` 覆盖 4 张表 + `alembic_version`。检查生成文件中 4 张表齐全（users / conversations / messages / ingest_jobs），缺表说明 env.py 模型导入失败，回查。

- [ ] **Step 4: 上库并验证**

```bash
uv run alembic upgrade head
uv run alembic current
docker exec medicalrag-mysql mysql -uroot -pmedicalrag medicalrag -e "show tables;"
```

Expected: `alembic current` 显示 head revision；`show tables` 输出 5 行：`alembic_version`、`conversations`、`ingest_jobs`、`messages`、`users`。

- [ ] **Step 5: 全量门禁**

```bash
uv run pytest -v && uv run ruff check . && uv run mypy app
```

Expected: 全 PASS / 0 错误（alembic 目录在 mypy overrides 中已豁免）。

- [ ] **Step 6: Commit**

```bash
cd .. && git add -A && git commit -m "feat: Alembic 异步迁移与首版 schema"
```

---

### Task 9: CI 工作流与 README 初版

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `README.md`
- Modify: `.gitignore`（如需补充 `.env.local` 等，一般无需）

**Interfaces:**
- Consumes: 全部前序任务的命令（uv sync / ruff / mypy / pytest）
- Produces: GitHub Actions CI（push main + PR 触发，backend lint→typecheck→test）；README 快速开始与项目结构说明

- [ ] **Step 1: 写 `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  backend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install uv
        uses: astral-sh/setup-uv@v5
      - name: Sync dependencies
        run: uv sync
      - name: Lint
        run: uv run ruff check .
      - name: Type check
        run: uv run mypy app
      - name: Test
        run: uv run pytest -v
```

- [ ] **Step 2: 写 `README.md`（初版，P8 再完善）**

````markdown
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

前置：Docker Desktop、uv、Python 3.12

```bash
cp .env.example .env      # 填入 LLM__API_KEY / EMBEDDING__API_KEY / RERANKER__API_KEY
make install              # 安装后端依赖
make infra-up             # 启动 Milvus + MySQL + Redis（首次拉镜像约数分钟）
make check-infra          # 连通性检查，期望三行 [ok]
cd backend && cp ../.env.example .env && uv run alembic upgrade head   # 建表
cd backend && uv run uvicorn app.main:app --reload --port 8000         # 启动 API
```

访问 `http://127.0.0.1:8000/docs` 查看 OpenAPI；`/api/v1/health` 返回三依赖探活。

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
````

- [ ] **Step 3: 本地全量门禁最后一遍**

```bash
cd backend && uv run pytest -v && uv run ruff check . && uv run mypy app
```

Expected: 全 PASS / 0 错误。

- [ ] **Step 4: Commit**

```bash
cd .. && git add -A && git commit -m "feat: GitHub Actions CI 与 README 初版"
```

---

## 任务依赖关系

```
Task 1 ─▶ Task 2 ─▶ Task 3 ─▶ Task 4 ──┐
              └─────▶ Task 5 ─▶ Task 6 ─┴─▶ Task 7 ─▶ Task 8 ─▶ Task 9
```

Task 4 依赖 Task 2（配置）；Task 6 依赖 Task 5（db）与 Task 3（中间件已挂载）；Task 8 依赖 Task 5 + Task 7；Task 9 收尾。
