"""Checkpoint 2 — disruption recovery integrated with the Scheduling Operations Agent.

Covers tool security (allowlist + event scope), multi-agent orchestration routing,
and the human-approval / no-partial-apply boundaries at the orchestration layer.
No UI is involved.
"""
from datetime import date

import pytest

from src.llm import MockAgentClient
from src.orchestration import AgentOrchestrator
from src.schemas.agent import AgentName, WorkflowStatus
from src.tools import ToolExecutionError, ToolExecutor, build_registry
from src.demo_scenarios import seed_sick_leave_scenario


DEMO_DAY = date(2030, 1, 20)


def _seed(db):
    return seed_sick_leave_scenario(db, DEMO_DAY)


# ----------------------------------------------------------------------------
# Registry / tool surface
# ----------------------------------------------------------------------------

def test_registry_has_disruption_tools_but_no_human_actions():
    registry = build_registry()
    assert "get_disruption_context" in registry
    assert "propose_recovery" in registry
    assert "get_recovery_plan" in registry
    # Approve / reject / apply / mutate must never be LLM tools.
    forbidden = {"approve_plan", "reject_plan", "recalculate_plan", "confirm_recommendation",
                 "apply_recovery", "approve_recovery", "reject_recovery"}
    assert forbidden.isdisjoint(registry.keys())


def test_disruption_tools_are_scheduling_only():
    registry = build_registry()
    for name in ("get_disruption_context", "propose_recovery", "get_recovery_plan"):
        allowed = registry[name].allowed_agents
        assert allowed == frozenset({AgentName.SCHEDULING.value})
        assert AgentName.INTAKE.value not in allowed


# ----------------------------------------------------------------------------
# B. Tool / security
# ----------------------------------------------------------------------------

def test_intake_agent_cannot_call_disruption_tools(db):
    scenario = _seed(db)
    orchestrator = AgentOrchestrator(db, MockAgentClient())
    result = orchestrator.run_disruption_recovery(
        scenario['technician_id'], scenario['unavailable_from'], scenario['unavailable_until'])
    event_id = result['event_id']
    executor = ToolExecutor(db, build_registry())
    with pytest.raises(ToolExecutionError):
        executor.execute(result['session_id'], AgentName.INTAKE.value,
                         "get_disruption_context", {"event_id": event_id})


def test_event_scope_rejects_event_outside_session(db):
    scenario = _seed(db)
    orchestrator = AgentOrchestrator(db, MockAgentClient())
    result = orchestrator.run_disruption_recovery(
        scenario['technician_id'], scenario['unavailable_from'], scenario['unavailable_until'])
    # A different session may not read this event.
    db.execute("INSERT INTO agent_sessions VALUES (?,?,?,?,?,?,?)",
        ("SES-OTHER", scenario['request_ids'][0], None, AgentName.SCHEDULING.value,
         "ASSIGNMENT_IN_PROGRESS", "now", "now"))
    db.commit()
    executor = ToolExecutor(db, build_registry())
    with pytest.raises(ToolExecutionError, match="outside its session"):
        executor.execute("SES-OTHER", AgentName.SCHEDULING.value,
                         "get_disruption_context", {"event_id": result['event_id']})


def test_unknown_event_id_fails_safely(db):
    _seed(db)
    db.execute("INSERT INTO agent_sessions VALUES (?,?,?,?,?,?,?)",
        ("SES-X", "DEMO-REQ-20300120-01", None, AgentName.SCHEDULING.value,
         "ASSIGNMENT_IN_PROGRESS", "now", "now"))
    # Map a bogus event so the scope check passes but the handler must fail on lookup.
    db.execute("INSERT INTO operational_events VALUES ('EVT-BOGUS','T001','UNAVAILABLE','x','y','r','OPEN','now')")
    db.execute("INSERT INTO disruption_sessions VALUES ('SES-X','EVT-BOGUS')")
    db.commit()
    executor = ToolExecutor(db, build_registry())
    # get_recovery_plan has no plan for this event -> safe ValueError, audited as ERROR.
    with pytest.raises(ToolExecutionError):
        executor.execute("SES-X", AgentName.SCHEDULING.value, "get_recovery_plan", {"event_id": "EVT-BOGUS"})
    audit = db.execute("SELECT execution_status FROM agent_tool_calls WHERE session_id='SES-X'").fetchone()
    assert audit['execution_status'] == "ERROR"


def test_extra_arguments_are_rejected(db):
    _seed(db)
    db.execute("INSERT INTO agent_sessions VALUES (?,?,?,?,?,?,?)",
        ("SES-Y", "DEMO-REQ-20300120-01", None, AgentName.SCHEDULING.value,
         "ASSIGNMENT_IN_PROGRESS", "now", "now"))
    db.commit()
    executor = ToolExecutor(db, build_registry())
    with pytest.raises(ToolExecutionError):
        executor.execute("SES-Y", AgentName.SCHEDULING.value, "get_disruption_context",
                         {"event_id": "E", "sneaky": "value"})


# ----------------------------------------------------------------------------
# C. Multi-agent orchestration
# ----------------------------------------------------------------------------

def test_disruption_routes_to_scheduling_and_not_intake(db):
    scenario = _seed(db)
    orchestrator = AgentOrchestrator(db, MockAgentClient())
    result = orchestrator.run_disruption_recovery(
        scenario['technician_id'], scenario['unavailable_from'], scenario['unavailable_until'])
    assert result['created_session'] is True
    agents = {row[0] for row in db.execute(
        "SELECT DISTINCT agent_name FROM agent_tool_calls WHERE session_id=?", (result['session_id'],))}
    assert agents == {AgentName.SCHEDULING.value}
    assert AgentName.INTAKE.value not in agents


def test_disruption_tool_trace_exists(db):
    scenario = _seed(db)
    orchestrator = AgentOrchestrator(db, MockAgentClient())
    result = orchestrator.run_disruption_recovery(
        scenario['technician_id'], scenario['unavailable_from'], scenario['unavailable_until'])
    tools = [row[0] for row in db.execute(
        "SELECT tool_name FROM agent_tool_calls WHERE session_id=? ORDER BY created_at", (result['session_id'],))]
    assert "get_disruption_context" in tools
    assert "propose_recovery" in tools
    assert "get_recovery_plan" in tools


def test_disruption_confirmed_change_routes_to_human_review(db):
    scenario = _seed(db)  # Three confirmed Alex jobs; recovery reassigns them.
    orchestrator = AgentOrchestrator(db, MockAgentClient())
    result = orchestrator.run_disruption_recovery(
        scenario['technician_id'], scenario['unavailable_from'], scenario['unavailable_until'])
    assert result['workflow_status'] == WorkflowStatus.HUMAN_REVIEW_REQUIRED
    assert result['handoffs'][-1]['handoff_type'] == "DISRUPTION_RECOVERY_PROPOSED"
    assert result['handoffs'][-1]['target_agent'] == "human_coordinator"


def test_disruption_with_no_affected_jobs_creates_no_session(db):
    # T004 (plumber) has no confirmed aircon jobs in the sick-leave demo window.
    _seed(db)
    orchestrator = AgentOrchestrator(db, MockAgentClient())
    result = orchestrator.run_disruption_recovery(
        "T004", f"{DEMO_DAY.isoformat()}T08:30", f"{DEMO_DAY.isoformat()}T16:00")
    assert result['created_session'] is False
    assert result['session_id'] is None
    assert result['plan']['plan']['affected_job_count'] == 0


def test_proposal_does_not_mutate_schedules_via_agent(db):
    scenario = _seed(db)
    before = db.execute("SELECT technician_id FROM schedules WHERE job_id=?",
                        (scenario['job_ids'][0],)).fetchone()['technician_id']
    orchestrator = AgentOrchestrator(db, MockAgentClient())
    orchestrator.run_disruption_recovery(
        scenario['technician_id'], scenario['unavailable_from'], scenario['unavailable_until'])
    after = db.execute("SELECT technician_id FROM schedules WHERE job_id=?",
                       (scenario['job_ids'][0],)).fetchone()['technician_id']
    assert before == after == "T001"  # Proposal only; no mutation until human approval.


# ----------------------------------------------------------------------------
# Week 1 normal flow still works (regression guard)
# ----------------------------------------------------------------------------

def test_week1_normal_request_still_works(db):
    response = AgentOrchestrator(db, MockAgentClient()).run_request(
        "R001", "C001", "aircon is leaking East 2025-01-15T10:00 2025-01-15T13:00")
    assert response.workflow_status == WorkflowStatus.RECOMMENDATION_CREATED
    agents = {row[0] for row in db.execute("SELECT DISTINCT agent_name FROM agent_tool_calls")}
    assert agents == {"customer_intake_agent", "scheduling_operations_agent"}
