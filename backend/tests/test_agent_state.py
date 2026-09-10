from app.agents.state import AgentResult, AgentState, QueryAnalysis, StepEvent, VerifyResult


def test_agent_state_defaults():
    s = AgentState(query="阿司匹林剂量")
    assert s.analysis is None
    assert s.iteration == 0 and s.regen_count == 0
    assert s.route == ""


def test_step_event_and_analysis():
    ev = StepEvent(name="retrieve", ms=123.4, detail="3 路子查询 → 24 chunks")
    a = QueryAnalysis(intent="risk", risk_type="chest_pain", reason="胸痛")
    s = AgentState(query="胸口疼", analysis=a)
    s.steps.append(ev)
    assert s.steps[0].detail.startswith("3 路")
    assert s.analysis is not None and s.analysis.intent == "risk"


def test_agent_result_export():
    r = AgentResult(route="answered", answer="……[1]", citations=[{"no": 1}])
    assert r.route == "answered" and len(r.citations) == 1


def test_verify_result():
    v = VerifyResult(passed=False, issues=["第 2 句无资料支持"])
    assert not v.passed
