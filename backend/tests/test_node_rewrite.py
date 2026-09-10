from app.agents.nodes.decompose import make_decompose_node
from app.agents.nodes.rewrite import make_rewrite_node
from app.agents.state import AgentState
from app.core.config import AgentSettings
from app.core.providers.llm import ChatMessage
from tests.test_node_analyze import ScriptedLLM


async def test_rewrite_resolves_coreference_with_history():
    llm = ScriptedLLM(['{"rewritten": "阿司匹林肠溶片的常用剂量是多少"}'])
    node = make_rewrite_node(llm)
    state = AgentState(
        query="它的剂量是多少",
        history=[
            ChatMessage(role="user", content="阿司匹林有什么作用"),
            ChatMessage(role="assistant", content="阿司匹林用于抗血小板…"),
        ],
    )
    update = await node(state)
    assert update["rewritten"] == "阿司匹林肠溶片的常用剂量是多少"
    assert update["iteration"] == 1
    # 历史确实进入了 prompt
    sent = llm.calls[0][-1].content
    assert "阿司匹林有什么作用" in sent


async def test_rewrite_includes_feedback():
    llm = ScriptedLLM(['{"rewritten": "妊娠期高血压的药物治疗方案"}'])
    node = make_rewrite_node(llm)
    state = AgentState(query="怀孕血压高吃什么药", feedback="最高分 0.2 低于阈值")
    await node(state)
    assert "上一次检索效果不佳" in llm.calls[0][-1].content


async def test_decompose_splits_comparison():
    llm = ScriptedLLM(['{"sub_queries": ["二甲双胍的适应证与用法", "SGLT2抑制剂的适应证与用法"]}'])
    node = make_decompose_node(llm, AgentSettings())
    state = AgentState(query="二甲双胍和SGLT2哪个好", rewritten="二甲双胍与SGLT2抑制剂比较")
    update = await node(state)
    assert update["sub_queries"] == [
        "二甲双胍的适应证与用法",
        "SGLT2抑制剂的适应证与用法",
    ]


async def test_decompose_caps_and_falls_back():
    # 超过上限截断
    llm = ScriptedLLM(['{"sub_queries": ["a", "b", "c", "d"]}'])
    node = make_decompose_node(llm, AgentSettings(subquery_max=3))
    update = await node(AgentState(query="q", rewritten="r"))
    assert len(update["sub_queries"]) == 3
    # 空输出兜底为改写查询
    llm2 = ScriptedLLM(['{"sub_queries": []}'])
    node2 = make_decompose_node(llm2, AgentSettings())
    update2 = await node2(AgentState(query="q", rewritten="改写后的查询"))
    assert update2["sub_queries"] == ["改写后的查询"]
