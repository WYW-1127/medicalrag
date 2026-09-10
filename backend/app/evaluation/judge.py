"""中文 LLM-as-Judge：忠实度与回答相关性（0-1 评分）。"""

from pydantic import BaseModel, Field

from app.agents.llm_io import ask_json
from app.core.providers.llm import LLMProvider

FAITHFULNESS_SYSTEM = """\
你是医学问答系统的质量评审。给定问题、回答和编号参考资料，评估回答的忠实度：
- 回答中的关键陈述（事实、数值、结论）是否都能在参考资料中找到支持
- 是否存在编造或与资料矛盾的内容

评分标准：
- 1.0：全部陈述有支持，无编造
- 0.5：大部分支持，个别陈述无法确认
- 0.0：存在明显编造或关键错误

只输出 JSON：{"score": 0.0~1.0, "issues": ["无支持的陈述1", ...]}（无问题时 issues 为空数组）"""

RELEVANCY_SYSTEM = """\
你是医学问答系统的质量评审。评估回答与问题的相关性：
- 回答是否切题，直接回应了用户所问
- 是否答非所问、绕开问题或只给出泛泛而谈

评分标准：
- 1.0：直接且完整地回答了问题
- 0.5：部分回应，有遗漏或偏题内容
- 0.0：答非所问

只输出 JSON：{"score": 0.0~1.0, "issues": ["问题描述", ...]}"""


class JudgeScore(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    issues: list[str] = Field(default_factory=list)


def _contexts_block(contexts: list[str]) -> str:
    return "\n\n".join(f"[{i}] {c[:800]}" for i, c in enumerate(contexts, 1))


async def judge_faithfulness(
    llm: LLMProvider, question: str, answer: str, contexts: list[str]
) -> JudgeScore:
    user = f"问题：{question}\n\n回答：\n{answer}\n\n参考资料：\n{_contexts_block(contexts)}"
    return await ask_json(llm, FAITHFULNESS_SYSTEM, user, JudgeScore)


async def judge_relevancy(llm: LLMProvider, question: str, answer: str) -> JudgeScore:
    return await ask_json(
        llm, RELEVANCY_SYSTEM, f"问题：{question}\n\n回答：\n{answer}", JudgeScore
    )
