from src.llm import MockAgentClient
from src.orchestration import AgentOrchestrator
from src.schemas.agent import WorkflowStatus


def test_agents_handoff_ready_request_and_audit_tools(db):
    response = AgentOrchestrator(db, MockAgentClient()).run_request(
        "R001", "C001", "aircon is leaking East 2025-01-15T10:00 2025-01-15T13:00")
    assert response.workflow_status == WorkflowStatus.RECOMMENDATION_CREATED
    assert [item["handoff_type"] for item in response.handoffs] == ["REQUEST_READY", "ASSIGNMENT_RECOMMENDED"]
    agents = {row[0] for row in db.execute("SELECT DISTINCT agent_name FROM agent_tool_calls")}
    assert agents == {"customer_intake_agent", "scheduling_operations_agent"}


def test_incomplete_request_stays_with_intake_agent(db):
    response = AgentOrchestrator(db, MockAgentClient()).run_request(
        "R010", "C010", "toilet blockage South")
    assert response.workflow_status == WorkflowStatus.NEEDS_CLARIFICATION
    assert response.handoffs[0]["handoff_type"] == "CUSTOMER_CLARIFICATION_REQUIRED"
    assert db.execute("SELECT COUNT(*) FROM assignment_results WHERE request_id='R010'").fetchone()[0] == 0


def test_customer_can_continue_same_session(db):
    orchestrator = AgentOrchestrator(db, MockAgentClient())
    first = orchestrator.run_request("R010", "C010", "toilet blockage South")
    second = orchestrator.continue_session(first.session_id, "2025-01-15T13:00 2025-01-15T17:00")
    assert second.session_id == first.session_id
    assert second.workflow_status == WorkflowStatus.RECOMMENDATION_CREATED
    assert db.execute("SELECT COUNT(*) FROM agent_sessions WHERE session_id=?", (first.session_id,)).fetchone()[0] == 1


def test_no_feasible_result_routes_to_human(db):
    db.execute("UPDATE customer_requests SET raw_message=? WHERE request_id='R001'", (
        "aircon is leaking East 2025-01-15T17:30 2025-01-15T18:00",))
    db.commit()
    response = AgentOrchestrator(db, MockAgentClient()).run_request(
        "R001", "C001", "aircon is leaking East 2025-01-15T17:30 2025-01-15T18:00")
    assert response.workflow_status == WorkflowStatus.NO_FEASIBLE_ASSIGNMENT
    assert response.handoffs[-1]["handoff_type"] == "HUMAN_REVIEW_REQUIRED"
