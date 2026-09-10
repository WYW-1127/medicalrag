"""五条路径的整图单测：正常回答 / 风险拦截 / 检索重试 / 再生成 / 拒答兜底。"""

from app.agents.graph import MedicalRAGAgent
from app.core.config import Settings
from app.rag.models import RetrievalResult, RetrievedChunk
from tests.test_node_analyze import ScriptedLLM

MEDICAL = '{"intent": "medical", "risk_type": "", "reason": "医学咨询"}'
RISK = '{"intent": "risk", "risk_type": "剧烈胸痛", "reason": "急症"}'
REWRITE = '{"rewritten": "高血压的诊断标准"}'
DECOMPOSE = '{"sub_queries": ["高血压的诊断标准"]}'
GRADE_OK = '{"scores": [0.9, 0.8]}'
GRADE_LOW = '{"scores": [0.1, 0.2]}'
VERIFY_OK = '{"passed": true, "issues": []}'
VERIFY_BAD = '{"passed": false, "issues": ["第1句无资料支持"]}'


class AnyRetriever:
    async def retrieve(self, query: str, **kwargs):  # type: ignore[no-untyped-def]
        chunks = [
            RetrievedChunk(chunk_id="c1", text="高血压诊断标准为收缩压≥140mmHg。",
                           source="高血压指南.pdf", section_path="诊断", page=3, rerank_score=0.9),
            RetrievedChunk(chunk_id="c2", text="分级：1级高血压为140-159mmHg。",
                           source="高血压指南.pdf", section_path="分级", page=4, rerank_score=0.8),
        ]
        return RetrievalResult(query=query, final=chunks)


def _agent(replies: list[str]) -> MedicalRAGAgent:
    return MedicalRAGAgent(
        llm=ScriptedLLM(replies),
        retriever=AnyRetriever(),  # type: ignore[arg-type]
        settings=Settings(_env_file=None),
    )


async def test_path_medical_happy():
    agent = _agent([
        MEDICAL, REWRITE, DECOMPOSE, GRADE_OK,
        "高血压的诊断标准是收缩压≥140mmHg[1]。",
        VERIFY_OK,
    ])
    result = await agent.run("血压多高算高血压")
    assert result.route == "answered"
    assert "140mmHg" in result.answer and "[1]" in result.answer
    assert result.citations and result.citations[0]["source"] == "高血压指南.pdf"
    names = [s.name for s in result.steps]
    assert names == ["analyze", "rewrite", "decompose", "retrieve", "grade", "generate", "verify"]


async def test_path_risk_intercepted():
    agent = _agent([RISK])
    result = await agent.run("胸口剧烈疼痛呼吸困难")
    assert result.route == "safe"
    assert "120" in result.answer
    assert [s.name for s in result.steps] == ["analyze", "safe_reply"]


async def test_path_grade_retry_then_success():
    agent = _agent([
        MEDICAL,
        REWRITE, DECOMPOSE, GRADE_LOW,   # 第一轮检索反思不达标 → retry
        REWRITE, DECOMPOSE, GRADE_OK,    # 第二轮达标
        "高血压的诊断标准是收缩压≥140mmHg[1]。",
        VERIFY_OK,
    ])
    result = await agent.run("血压标准")
    assert result.route == "answered"
    names = [s.name for s in result.steps]
    assert names.count("rewrite") == 2 and names.count("grade") == 2


async def test_path_verify_fail_then_regen():
    agent = _agent([
        MEDICAL, REWRITE, DECOMPOSE, GRADE_OK,
        "编造的回答：高血压需要立即手术[1]。",   # 首版无法通过校验
        VERIFY_BAD,
        "修正后的回答：高血压的诊断标准是收缩压≥140mmHg[1]。",
        VERIFY_OK,
    ])
    result = await agent.run("高血压诊断标准")
    assert result.route == "answered"
    assert "140mmHg" in result.answer
    names = [s.name for s in result.steps]
    assert names.count("generate") == 2 and names.count("verify") == 2


async def test_path_grade_exhausted_fallback():
    agent = _agent([
        MEDICAL,
        REWRITE, DECOMPOSE, GRADE_LOW,
        REWRITE, DECOMPOSE, GRADE_LOW,   # 迭代耗尽 → 拒答
    ])
    result = await agent.run("量子力学与血糖的关系")
    assert result.route == "fallback"
    assert "无法可靠回答" in result.answer
    names = [s.name for s in result.steps]
    assert "fallback" in names and "generate" not in names
