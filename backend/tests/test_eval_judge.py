from app.evaluation.judge import judge_faithfulness, judge_relevancy
from tests.test_node_analyze import ScriptedLLM

FAITH_OK = '{"score": 1.0, "issues": []}'
FAITH_BAD = '{"score": 0.0, "issues": ["剂量陈述无资料支持"]}'
REL_OK = '{"score": 1.0, "issues": []}'


async def test_judge_faithfulness_parses():
    llm = ScriptedLLM([FAITH_OK])
    s = await judge_faithfulness(llm, "q", "回答[1]", ["资料"])
    assert s.score == 1.0 and s.issues == []
    sent = llm.calls[0][-1].content
    assert "资料" in sent and "回答[1]" in sent


async def test_judge_faithfulness_issues():
    llm = ScriptedLLM([FAITH_BAD])
    s = await judge_faithfulness(llm, "q", "编造的回答", ["资料"])
    assert s.score == 0.0 and s.issues[0].startswith("剂量")


async def test_judge_relevancy():
    llm = ScriptedLLM([REL_OK])
    s = await judge_relevancy(llm, "q", "a")
    assert s.score == 1.0


async def test_judge_score_bounds():
    llm = ScriptedLLM(['{"score": 1.5, "issues": []}'] * 2)  # 越界 → 重试也失败 → 抛错
    import pytest

    from app.core.providers.llm import ProviderError

    with pytest.raises(ProviderError):
        await judge_relevancy(llm, "q", "a")
