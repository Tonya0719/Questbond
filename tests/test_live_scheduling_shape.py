from dataclasses import replace

from src.agents import scheduling_operations_agent as module
from src.schemas.agent import AgentName
from src.tools import ToolExecutor, build_registry


class ToolCallingClient:
    def __init__(self):
        self.turn = 0

    def converse(self, messages, system_prompt, tools):
        self.turn += 1
        content = ([{"toolUse": {"toolUseId": "call-1", "name": "recommend_assignment", "input": {"request_id": "R001"}}}]
                   if self.turn == 1 else [{"text": "Recommendation created from the tool result."}])
        return {"output": {"message": {"role": "assistant", "content": content}}}


def test_tool_calling_backend_preserves_assignment_fields(db, monkeypatch):
    monkeypatch.setattr(module, "settings", replace(module.settings, llm_backend="bedrock"))
    db.execute("INSERT INTO agent_sessions VALUES (?,?,?,?,?,?,?)", (
        "SES-LIVE", "R001", "C001", AgentName.SCHEDULING.value, "ASSIGNMENT_IN_PROGRESS", "now", "now"))
    db.commit()
    registry = build_registry()
    result = module.SchedulingOperationsAgent(ToolExecutor(db, registry), registry, ToolCallingClient()).run("SES-LIVE", "R001")
    assert result["assignment"]["technician_id"] == "T002"
    assert result["assignment"]["scheduled_start"]
    assert result["validation"]["valid"]
    assert result["decision_trace"]["selected_candidate"]["technician_id"] == "T002"
