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
