from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.providers.llm import ChatMessage
from app.rag.models import RetrievedChunk

# 节点返回的局部状态更新（langgraph 约定）
NodeUpdate = dict[str, Any]


class StepEvent(BaseModel):
    """节点执行事件：前端检索时间线与 P5 SSE step 事件的数据源。"""

    name: str
    ms: float
    detail: str = ""


class QueryAnalysis(BaseModel):
    """analyze 节点输出：意图分类与风险标记。"""

    intent: Literal["medical", "chitchat", "risk"]
    risk_type: str = ""
    reason: str = ""


class VerifyResult(BaseModel):
    """verify 节点输出：引用忠实度校验结论。"""

    passed: bool
    issues: list[str] = []


class AgentState(BaseModel):
    """LangGraph 图状态。每个节点返回局部字段更新。"""

    query: str
    history: list[ChatMessage] = Field(default_factory=list)

    analysis: QueryAnalysis | None = None
    rewritten: str = ""
    sub_queries: list[str] = Field(default_factory=list)
    feedback: str = ""  # grade 失败时带给 rewrite 的反思反馈
    iteration: int = 0

    chunks: list[RetrievedChunk] = Field(default_factory=list)
    grades: list[float] = Field(default_factory=list)

    answer: str = ""
    citations: list[dict[str, Any]] = Field(default_factory=list)
    verify: VerifyResult | None = None
    regen_count: int = 0

    steps: list[StepEvent] = Field(default_factory=list)
    route: str = ""  # answered | safe | fallback


class AgentResult(BaseModel):
    """对 P5 API 层的稳定出口。"""

    route: str
    answer: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    steps: list[StepEvent] = Field(default_factory=list)
