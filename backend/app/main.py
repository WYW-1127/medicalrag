from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.router import api_router
from app.core.config import get_settings
from app.core.db import get_session_factory
from app.core.logging import setup_logging
from app.core.middleware import TraceIDMiddleware


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        setup_logging(debug=settings.debug)
        app.state.session_factory = lambda: get_session_factory(settings.database_url)
        # Agent 懒加载标记：首个 chat 请求时构造（Milvus/LLM 配置就绪后）
        app.state.agent = None
        try:
            from app.agents.graph import MedicalRAGAgent

            app.state.agent = MedicalRAGAgent(settings=settings)
        except Exception as exc:  # noqa: BLE001 启动不因下游不可用而崩溃，请求时给 503
            logger.warning("Agent 初始化失败（将在请求时重试）: {}", exc)
        yield

    app = FastAPI(title="MedicalRAG API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(TraceIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],  # 前端 dev server
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
