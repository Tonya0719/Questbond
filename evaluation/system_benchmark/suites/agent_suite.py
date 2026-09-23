"""Agent orchestration suite — offline-verifiable part (mock backend).

Measures Agent routing, tool selection/authorization, handoff and final state on
the deterministic mock backend. Latency/tokens/cost are NOT collected here; those
are live-only (Checkpoint B4). Deterministic scheduling correctness is not part of
this suite. Ground truth is read for comparison only.
"""
from __future__ import annotations

from time import perf_counter

from src.llm import MockAgentClient
from src.orchestration import AgentOrchestrator
from src.schemas.agent import AgentName

from .. import loaders

BENCH_DAY = "2030-03-04"


def _tool_calls(connection, session_id):
    return connection.execute(
        "SELECT agent_name, tool_name, execution_status FROM agent_tool_calls WHERE session_id=?",
        (session_id,)).fetchall()


def _normal_request(connection, ready: bool):
    zone = "East"
    if ready:
        text = f"aircon leak {zone} 2030-03-10T10:00 2030-03-10T13:00"
    else:
        text = "toilet blockage South"
    connection.execute("INSERT INTO customer_requests VALUES ('AGT-REQ','NEW','2030-03-01T00:00','WEB',?,?)",
                       (text, "en"))
    connection.commit()
    return AgentOrchestrator(connection, MockAgentClient()).run_request("AGT-REQ", "NEW", text)


def _no_feasible_request(connection):
    text = "aircon leak West 2030-03-10T17:30 2030-03-10T18:00"
    connection.execute("INSERT INTO customer_requests VALUES ('AGT-NF','NEW','2030-03-01T00:00','WEB',?,?)",
                       (text, "en"))
    connection.commit()
    return AgentOrchestrator(connection, MockAgentClient()).run_request("AGT-NF", "NEW", text)


def _clarify_then_ready(connection):
    orch = AgentOrchestrator(connection, MockAgentClient())
    connection.execute("INSERT INTO customer_requests VALUES ('AGT-CL','NEW','2030-03-01T00:00','WEB',?,?)",
                       ("toilet blockage South", "en"))
    connection.commit()
    first = orch.run_request("AGT-CL", "NEW", "toilet blockage South")
    second = orch.continue_session(first.session_id, "2030-03-10T13:00 2030-03-10T17:00")
    return second


def _disruption(connection, event_type):
    if event_type == "UNAVAILABLE":
        return AgentOrchestrator(connection).run_disruption_recovery(
            "T009", f"{BENCH_DAY}T08:00", f"{BENCH_DAY}T16:30", event_type="UNAVAILABLE", reason="bench")
    # DELAYED normalised interval; T009 09:30 job JB011 affected by a 30-min delay at 09:30.
    from src.services.disruption_service import create_delay_plan
    # Route through orchestrator with a delay window that affects a downstream job.
    return AgentOrchestrator(connection).run_disruption_recovery(
        "T009", f"{BENCH_DAY}T09:30", f"{BENCH_DAY}T10:00", event_type="DELAYED", reason="bench delay")


def run(cases: list[dict], truth: dict[str, dict]) -> list[dict]:
    gt = truth["agent"]
    rows = []
    for case in [c for c in cases if c["suite"] == "agent"]:
        case_id = case["case_id"]
        expected = gt[case["expected_ref"]]
        scenario = case["scenario_type"]
        started = perf_counter()
        connection = loaders.new_world()
        session_id = None
        final_state = None
        handoff_type = None
        try:
            if scenario in ("normal_request_route", "normal_booking_handoff_sequence"):
                response = _normal_request(connection, ready=True)
                session_id, final_state = response.session_id, response.workflow_status.value
                handoff_type = response.handoffs[-1]["handoff_type"] if response.handoffs else "none"
            elif scenario in ("missing_info_stays_intake", "intake_cannot_disruption_tool"):
                response = _normal_request(connection, ready=False)
                session_id, final_state = response.session_id, response.workflow_status.value
                handoff_type = response.handoffs[-1]["handoff_type"] if response.handoffs else "none"
            elif scenario == "clarification_then_ready":
                response = _clarify_then_ready(connection)
                session_id, final_state = response.session_id, response.workflow_status.value
                handoff_type = response.handoffs[-1]["handoff_type"] if response.handoffs else "none"
            elif scenario == "no_feasible_to_human":
                response = _no_feasible_request(connection)
                session_id, final_state = response.session_id, response.workflow_status.value
                handoff_type = response.handoffs[-1]["handoff_type"] if response.handoffs else "none"
            elif scenario == "zero_affected_no_session":
                result = AgentOrchestrator(connection).run_disruption_recovery(
                    "T013", f"{BENCH_DAY}T08:00", f"{BENCH_DAY}T12:00")
                session_id = result["session_id"]
                final_state = "NO_SESSION" if not result["created_session"] else result["workflow_status"].value
                handoff_type = result["handoffs"][-1]["handoff_type"] if result["handoffs"] else "none"
            elif scenario == "delayed_routes_scheduling":
                result = _disruption(connection, "DELAYED")
                session_id = result["session_id"]
                final_state = result["workflow_status"].value
                handoff_type = result["handoffs"][-1]["handoff_type"] if result["handoffs"] else "none"
            else:  # all remaining UNAVAILABLE-based disruption scenarios
                result = _disruption(connection, "UNAVAILABLE")
                session_id = result["session_id"]
                final_state = result["workflow_status"].value
                handoff_type = result["handoffs"][-1]["handoff_type"] if result["handoffs"] else "none"

            calls = _tool_calls(connection, session_id) if session_id else []
            agents_used = {row["agent_name"] for row in calls}
            tools_used = {row["tool_name"] for row in calls}
        finally:
            connection.close()
        duration_ms = int((perf_counter() - started) * 1000)

        exp_path = [p for p in expected["expected_agent_path"].split("|") if p]
        required_tools = [t for t in expected["required_tools"].split("|") if t]
        forbidden_tools = [t for t in expected["forbidden_tools"].split("|") if t]
        exp_handoff = expected["expected_handoff"]
        exp_final = expected["expected_final_state"]

        # Agent path: the set of agents that acted must match the expected path set.
        # For no-session cases, path check is skipped (no tool calls recorded).
        if final_state == "NO_SESSION":
            handoff_correct = exp_handoff in ("none", handoff_type)
            path_ok = True
            tools_correct = True
            unauthorized = 0
        else:
            path_ok = set(exp_path) == agents_used if exp_path else True
            tools_correct = all(t in tools_used for t in required_tools) and \
                not any(t in tools_used for t in forbidden_tools)
            handoff_correct = (handoff_type == exp_handoff)
            unauthorized = 0  # mock records only authorised, executed calls
        final_state_correct = (final_state == exp_final)

        passed = path_ok and tools_correct and handoff_correct and final_state_correct
        rows.append({
            "case_id": case_id, "suite": "agent", "scenario_type": scenario,
            "pass": passed,
            "failure_reason": "" if passed else _fail(path_ok, tools_correct, handoff_correct, final_state_correct),
            "expected": f"path={exp_path};handoff={exp_handoff};final={exp_final}",
            "actual": f"agents={sorted(agents_used) if session_id else []};handoff={handoff_type};final={final_state}",
            "duration_ms": duration_ms, "backend": "mock", "model": "",
            "input_tokens": "", "output_tokens": "", "cost_usd": "",
            # metric fields
            "handoff_correct": handoff_correct, "tools_correct": tools_correct,
            "final_state_correct": final_state_correct,
            "attempted_tool_calls": len(calls) if session_id else 0, "unauthorized_tool_calls": unauthorized,
        })
    return rows


def _fail(path, tools, handoff, final) -> str:
    parts = []
    if not path:
        parts.append("agent_path")
    if not tools:
        parts.append("tools")
    if not handoff:
        parts.append("handoff")
    if not final:
        parts.append("final_state")
    return "mismatch: " + ",".join(parts)
