import pytest

from app.agents.llm_io import ask_json, extract_json
from app.agents.nodes.analyze import make_analyze_node, route_after_analyze
from app.agents.nodes.safe_reply import safe_reply_node
from app.agents.state import AgentState, QueryAnalysis
from app.core.providers.llm import ProviderError
from tests.conftest import ScriptedLLM


# ---- llm_io ----
def test_extract_json_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced_and_noise():
    text = '好的，以下是结果：\n```json\n{"intent": "risk"}\n```\n希望有帮助'
    assert extract_json(text) == {"intent": "risk"}


def test_extract_json_embedded():
    assert extract_json('前缀 {"x": [1,2]} 后缀') == {"x": [1, 2]}


async def test_ask_json_parses_and_validates():
    llm = ScriptedLLM(['{"intent": "medical", "risk_type": "", "reason": "用药咨询"}'])
    result = await ask_json(llm, "sys", "q", QueryAnalysis)
    assert result.intent == "medical"


async def test_ask_json_retries_then_raises():
    llm = ScriptedLLM(["这不是json", "还是不是"])
    with pytest.raises(ProviderError):
        await ask_json(llm, "sys", "q", QueryAnalysis)
    assert len(llm.calls) == 2  # 重试了一次
    assert "无法解析" in llm.calls[1][-1].content  # 失败原因回传给了 LLM


# ---- analyze ----
async def test_analyze_node_medical():
    llm = ScriptedLLM(['{"intent": "medical", "risk_type": "", "reason": "剂量咨询"}'])
    node = make_analyze_node(llm)
    update = await node(AgentState(query="阿司匹林剂量"))
    assert update["analysis"].intent == "medical"  # type: ignore[union-attr]
    assert update["steps"][-1].name == "analyze"  # type: ignore[index]


def test_route_after_analyze():
    risk = AgentState(query="q", analysis=QueryAnalysis(intent="risk", risk_type="胸痛"))
    chat = AgentState(query="q", analysis=QueryAnalysis(intent="chitchat"))
    med = AgentState(query="q", analysis=QueryAnalysis(intent="medical"))
    assert route_after_analyze(risk) == "safe"
    assert route_after_analyze(chat) == "safe"
    assert route_after_analyze(med) == "medical"
    assert route_after_analyze(AgentState(query="q")) == "safe"  # 分析失败按安全处理


# ---- safe_reply ----
async def test_safe_reply_risk_template():
    state = AgentState(
        query="胸口剧痛", analysis=QueryAnalysis(intent="risk", risk_type="剧烈胸痛")
    )
    update = await safe_reply_node(state)
    assert update["route"] == "safe"
    assert "120" in update["answer"]


async def test_safe_reply_chitchat():
    state = AgentState(query="你好", analysis=QueryAnalysis(intent="chitchat"))
    update = await safe_reply_node(state)
    assert "医学知识问答助手" in update["answer"]
