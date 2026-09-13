import pytest

from src.schemas.agent import AgentName
from src.tools import ToolExecutionError, ToolExecutor, build_registry


def _session(db):
    db.execute("INSERT INTO agent_sessions VALUES (?,?,?,?,?,?,?)",
        ("SES-TEST", "R001", "C001", AgentName.INTAKE.value, "COLLECTING_INFORMATION", "now", "now"))
    db.commit()


def test_tool_allowlist_blocks_cross_agent_access(db):
    _session(db)
    executor = ToolExecutor(db, build_registry())
    with pytest.raises(ToolExecutionError):
        executor.execute("SES-TEST", AgentName.INTAKE.value, "recommend_assignment", {"request_id": "R001"})
    audit = db.execute("SELECT * FROM agent_tool_calls WHERE session_id='SES-TEST'").fetchone()
    assert audit["execution_status"] == "ERROR"


def test_intake_tool_derives_rule_fields(db):
    _session(db)
    executor = ToolExecutor(db, build_registry())
    result = executor.execute("SES-TEST", AgentName.INTAKE.value, "save_structured_request", {
        "request_id": "R001", "customer_id": "C001", "service_rule_id": "AC-LEAK", "zone": "East",
        "window_start": "2025-01-15T10:00", "window_end": "2025-01-15T13:00"})
    assert result["category"] == "Air-conditioning"
    assert result["estimated_duration_min"] == 90
    assert result["ready_for_scheduling"] is True


def test_assignment_tool_returns_validated_trace(db):
    _session(db)
    db.execute("UPDATE agent_sessions SET current_agent=? WHERE session_id='SES-TEST'", (AgentName.SCHEDULING.value,))
    db.commit()
    executor = ToolExecutor(db, build_registry())
    assignment = executor.execute("SES-TEST", AgentName.SCHEDULING.value,
                                  "recommend_assignment", {"request_id": "R001"})
    validation = executor.execute("SES-TEST", AgentName.SCHEDULING.value,
        "validate_assignment_recommendation", {"assignment_id": assignment["assignment_id"]})
    trace = executor.execute("SES-TEST", AgentName.SCHEDULING.value,
        "get_assignment_decision_trace", {"assignment_id": assignment["assignment_id"]})
    assert validation == {"assignment_id": assignment["assignment_id"], "valid": True, "violations": []}
    assert trace["selected_candidate"]["technician_id"] == "T002"
    assert trace["eligible_candidates"]
