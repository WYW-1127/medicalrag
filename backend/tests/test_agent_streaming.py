"""Agent 流式化测试：step 事件序、token sink、无 sink 回归。"""

from app.agents.graph import MedicalRAGAgent
from app.agents.streaming import token_sink
from app.core.config import Settings
from app.core.providers.llm import ChatMessage, LLMProvider
from app.rag.models import RetrievalResult, RetrievedChunk

MEDICAL = '{"intent": "medical", "risk_type": "", "reason": "r"}'
REWRITE = '{"rewritten": "高血压诊断标准"}'
DECOMPOSE = '{"sub_queries": ["高血压诊断标准"]}'
GRADE_OK = '{"scores": [0.9, 0.8]}'
VERIFY_OK = '{"passed": true, "issues": []}'
ANSWER = "高血压的诊断标准是收缩压≥140mmHg[1]。"


class StreamingScriptLLM(LLMProvider):
    """chat 整段返回脚本；chat_stream 按三段切分流式返回（模拟增量）。"""

    def __init__(self, replies: list[str], stream_text: str) -> None:
        self.replies = list(replies)
        self.stream_text = stream_text

    async def chat(self, messages, *, temperature=None):  # type: ignore[no-untyped-def]
        return self.replies.pop(0)

    async def chat_stream(self, messages, *, temperature=None):  # type: ignore[no-untyped-def]
        for i in range(0, len(self.stream_text), 7):
            yield self.stream_text[i : i + 7]


class AnyRetriever:
    async def retrieve(self, query: str, **kwargs):  # type: ignore[no-untyped-def]
        chunks = [
            RetrievedChunk(chunk_id="c1", text="高血压诊断标准为收缩压≥140mmHg。",
                           source="g.pdf", section_path="诊断", page=1, rerank_score=0.9),
            RetrievedChunk(chunk_id="c2", text="分级内容。", source="g.pdf",
                           section_path="分级", page=2, rerank_score=0.8),
        ]
        return RetrievalResult(query=query, final=chunks)


def _agent(stream_text: str) -> MedicalRAGAgent:
    llm = StreamingScriptLLM(
        [MEDICAL, REWRITE, DECOMPOSE, GRADE_OK, VERIFY_OK], stream_text
    )
    return MedicalRAGAgent(
        llm=llm, retriever=AnyRetriever(), settings=Settings(_env_file=None)  # type: ignore[arg-type]
    )


async def test_run_streaming_steps_and_result():
    agent = _agent(ANSWER)
    events = []
    token_sink.set(lambda _t: None)  # 走流式生成分支（token 断言在下一个测试）
    try:
        async for kind, payload in agent.run_streaming("血压标准"):
            events.append((kind, payload))
    finally:
        token_sink.set(None)
    kinds = [k for k, _ in events]
    assert kinds == ["step"] * 7 + ["result"]
    names = [p.name for k, p in events if k == "step"]
    assert names == ["analyze", "rewrite", "decompose", "retrieve", "grade", "generate", "verify"]
    result = events[-1][1]
    assert result.route == "answered" and "140mmHg" in result.answer


async def test_token_sink_receives_stream():
    agent = _agent(ANSWER)
    tokens: list[str] = []
    token_sink.set(tokens.append)
    try:
        async for _ in agent.run_streaming("血压标准"):
            pass
    finally:
        token_sink.set(None)
    # ANSWER 按 7 字符切段流式输出，拼接应等于原文
    assert "".join(tokens) == ANSWER


async def test_run_without_sink_still_works():
    """旧路径回归：不设 sink 时 chat 整段返回（StreamingScriptLLM.chat 走脚本）。"""

    class ScriptLLM(LLMProvider):
        def __init__(self, replies: list[str]) -> None:
            self.replies = list(replies)

        async def chat(self, messages, *, temperature=None):  # type: ignore[no-untyped-def]
            return self.replies.pop(0)

    llm = ScriptLLM([MEDICAL, REWRITE, DECOMPOSE, GRADE_OK, ANSWER, VERIFY_OK])
    agent = MedicalRAGAgent(
        llm=llm, retriever=AnyRetriever(), settings=Settings(_env_file=None)  # type: ignore[arg-type]
    )
    result = await agent.run("血压标准")
    assert result.route == "answered"


async def test_history_passed_through():
    """history 传入后 rewrite 的 prompt 中包含历史（多轮指代消解数据源）。"""

    captured: list[list[ChatMessage]] = []

    class CaptureLLM(LLMProvider):
        def __init__(self, replies: list[str]) -> None:
            self.replies = list(replies)

        async def chat(self, messages, *, temperature=None):  # type: ignore[no-untyped-def]
            captured.append(list(messages))
            return self.replies.pop(0)

    llm = CaptureLLM([MEDICAL, REWRITE, DECOMPOSE, GRADE_OK, ANSWER, VERIFY_OK])
    agent = MedicalRAGAgent(
        llm=llm, retriever=AnyRetriever(), settings=Settings(_env_file=None)  # type: ignore[arg-type]
    )
    history = [ChatMessage(role="user", content="阿司匹林的作用")]
    await agent.run("它的剂量呢", history=history)
    rewrite_user_msg = captured[1][-1].content  # rewrite 调用的 user 内容
    assert "阿司匹林的作用" in rewrite_user_msg
