from app.agents.nodes.fallback import fallback_node
from app.agents.nodes.generate import build_context, make_generate_node, parse_citations
from app.agents.nodes.verify import make_verify_node, route_after_verify
from app.agents.state import AgentState, VerifyResult
from app.rag.models import RetrievedChunk
from tests.conftest import ScriptedLLM


def _chunks():
    return [
        RetrievedChunk(
            chunk_id="c1", text="高血压诊断标准为收缩压≥140mmHg。",
            source="高血压指南.pdf", section_path="诊断", page=3,
        ),
        RetrievedChunk(
            chunk_id="c2", text="常用降压药包括CCB、ACEI、ARB等。",
            source="高血压指南.pdf", section_path="治疗", page=10,
        ),
    ]


def test_parse_citations_extracts_and_maps():
    answer = "诊断标准是收缩压≥140mmHg[1]。药物选择包括多种类别[2][1]。"
    _, citations = parse_citations(answer, _chunks())
    assert [c["no"] for c in citations] == [1, 2]  # 重复 [1] 去重
    assert citations[0]["source"] == "高血压指南.pdf"
    assert citations[0]["page"] == 3


def test_parse_citations_out_of_range_ignored():
    _, citations = parse_citations("陈述[9]", _chunks())
    assert citations == []


def test_build_context_numbered():
    text = build_context(_chunks())
    assert text.startswith("[1]（来源：高血压指南.pdf")
    assert "[2]" in text


async def test_generate_node_appends_disclaimer_and_citations():
    llm = ScriptedLLM(["高血压的诊断标准是收缩压≥140mmHg[1]。"])
    node = make_generate_node(llm)
    update = await node(AgentState(query="高血压诊断标准", chunks=_chunks()))
    assert "⚠️" in update["answer"]
    assert len(update["citations"]) == 1
    assert update["regen_count"] == 1


async def test_generate_node_absorbs_verify_issues():
    llm = ScriptedLLM(["修正后的回答：收缩压≥140mmHg[1]。"])
    node = make_generate_node(llm)
    state = AgentState(
        query="q", chunks=_chunks(),
        verify=VerifyResult(passed=False, issues=["引用[2]无资料支持"]),
    )
    update = await node(state)
    assert "引用[2]无资料支持" in llm.calls[0][-1].content  # issues 回传给了 LLM
    assert update["regen_count"] == 1


async def test_verify_node_pass():
    llm = ScriptedLLM(['{"passed": true, "issues": []}'])
    node = make_verify_node(llm)
    state = AgentState(
        query="q", chunks=_chunks(), answer="标准是140[1]",
        citations=[
            {"no": 1, "chunk_id": "c1", "text": "…",
             "source": "s", "section_path": "", "page": 1},
        ],
    )
    update = await node(state)
    assert update["verify"].passed is True  # type: ignore[union-attr]


async def test_verify_node_no_citations_fails_without_llm():
    llm = ScriptedLLM([])  # 无调用预算：无引用时不应调 LLM
    node = make_verify_node(llm)
    update = await node(AgentState(query="q", chunks=_chunks(), answer="无引用回答"))
    assert not update["verify"].passed  # type: ignore[union-attr]
    assert not llm.calls


def test_route_after_verify():
    ok = AgentState(query="q", verify=VerifyResult(passed=True))
    fail_can_regen = AgentState(
        query="q", verify=VerifyResult(passed=False, issues=["x"]), regen_count=1
    )
    fail_exhausted = AgentState(
        query="q", verify=VerifyResult(passed=False, issues=["x"]), regen_count=2
    )
    assert route_after_verify(ok, 1) == "end"
    assert route_after_verify(fail_can_regen, 1) == "regenerate"
    assert route_after_verify(fail_exhausted, 1) == "fallback"


async def test_fallback_reply():
    update = await fallback_node(AgentState(query="q"))
    assert update["route"] == "fallback"
    assert "无法可靠回答" in update["answer"]
    assert "⚠️" in update["answer"]
