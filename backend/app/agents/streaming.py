"""流式输出的进程内通道：generate 节点把 token 逐个推给 API 层。

用法：API 层在启动 agent 的 task 内 `token_sink.set(callback)`，
generate 节点检测到 sink 时走 chat_stream 逐 token 回调。
asyncio 同 task 内 contextvar 可见（langgraph async 节点直接 await，不跨线程）。
"""

import contextvars
from collections.abc import Callable

token_sink: contextvars.ContextVar[Callable[[str], None] | None] = contextvars.ContextVar(
    "token_sink", default=None
)
