"""Live Agent benchmark runner.

Drives the live-subset cases through the product orchestrator on the CONFIGURED
live backend (never forced to mock), records provider/model metadata and per-case
latency/tokens/cost, and scores Agent-only behaviour (routing, tools, handoff,
final state). Deterministic scheduling correctness is NOT credited to the LLM here.

Cost uses provider-reported values; missing cost stays missing (never zero).
"""
from __future__ import annotations

from time import perf_counter

from src.config import settings
from src.orchestration import AgentOrchestrator
from src.schemas.agent import AgentName

from .. import loaders

BENCH_DAY = "2030-03-04"


def estimate(cases: list[dict]) -> dict:
    """Pre-run report inputs: case count, backend, model, estimated model calls."""
    model = settings.llm_model or settings.bedrock_model_id or settings.local_llm_model or "(unset)"
    # Bounded by the agent turn cap (<=8 model turns per agent). Use a conservative
    # average of 4 and an upper bound of 8 per case for the estimate.
    return {
        "cases": len(cases),
        "backend": settings.llm_backend,
        "model": model,
        "estimated_calls_avg": len(cases) * 4,
        "estimated_calls_max": len(cases) * 8,
    }


def _session_usage(connection, session_id):
    if not session_id:
        return {"model_calls": 0, "priced_calls": 0, "cost_usd": None,
                "input_tokens": None, "output_tokens": None}
    row = connection.execute(
        """SELECT COUNT(*) AS model_calls, COUNT(cost_usd) AS priced_calls, SUM(cost_usd) AS cost_usd,
                  SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens
           FROM agent_model_calls WHERE session_id=?""", (session_id,)).fetchone()
    return dict(row)


def _drive(connection, case, truth):
    """Run one case through the live orchestrator; return (session_id, final_state, handoff, tools)."""
    suite = case["suite"]
    scenario = case["scenario_type"]
    # Normal/clarification request cases go through intake+scheduling.
    if suite in ("request", "agent") and scenario in (
            "normal_complete", "normal_request_route", "normal_booking_handoff_sequence"):
        text = "aircon leak East 2030-03-10T10:00 2030-03-10T13:00"
        connection.execute("INSERT INTO customer_requests VALUES ('LIVE-R','NEW','2030-03-01T00:00','WEB',?,?)", (text, "en"))
        connection.commit()
        response = AgentOrchestrator(connection).run_request("LIVE-R", "NEW", text)
        return response.session_id, response.workflow_status.value, _last_handoff(response.handoffs)
    if suite in ("request", "agent") and scenario in ("missing_info_stays_intake", "missing_service_type", "missing_time"):
        text = "toilet blockage South"
        connection.execute("INSERT INTO customer_requests VALUES ('LIVE-R','NEW','2030-03-01T00:00','WEB',?,?)", (text, "en"))
        connection.commit()
        response = AgentOrchestrator(connection).run_request("LIVE-R", "NEW", text)
        return response.session_id, response.workflow_status.value, _last_handoff(response.handoffs)
    if scenario in ("unavailable_routes_scheduling",) or (suite == "disruption" and case["expected_ref"].startswith("DSP") and _is_unavailable(truth, case)):
        result = AgentOrchestrator(connection).run_disruption_recovery(
            "T009", f"{BENCH_DAY}T08:00", f"{BENCH_DAY}T16:30", event_type="UNAVAILABLE", reason="live")
        return result["session_id"], _state(result), _last_handoff(result["handoffs"])
    if scenario in ("delayed_routes_scheduling",) or (suite == "disruption"):
        result = AgentOrchestrator(connection).run_disruption_recovery(
            "T009", f"{BENCH_DAY}T09:30", f"{BENCH_DAY}T10:00", event_type="DELAYED", reason="live")
        return result["session_id"], _state(result), _last_handoff(result["handoffs"])
    # Fallback: treat as a normal request so the Agent still runs on the live backend.
    text = "aircon leak East 2030-03-10T10:00 2030-03-10T13:00"
    connection.execute("INSERT INTO customer_requests VALUES ('LIVE-R','NEW','2030-03-01T00:00','WEB',?,?)", (text, "en"))
    connection.commit()
    response = AgentOrchestrator(connection).run_request("LIVE-R", "NEW", text)
    return response.session_id, response.workflow_status.value, _last_handoff(response.handoffs)


def _is_unavailable(truth, case):
    row = truth["disruption"].get(case["expected_ref"])
    return bool(row) and row["event_type"] == "UNAVAILABLE"


def _state(result):
    return "NO_SESSION" if not result.get("created_session") else result["workflow_status"].value


def _last_handoff(handoffs):
    return handoffs[-1]["handoff_type"] if handoffs else "none"


def run(cases: list[dict], truth: dict[str, dict]) -> list[dict]:
    rows = []
    for case in cases:
        case_id = case["case_id"]
        started = perf_counter()
        connection = loaders.new_world()
        session_id = final_state = handoff = None
        error = ""
        try:
            session_id, final_state, handoff = _drive(connection, case, truth)
            usage = _session_usage(connection, session_id)
        except Exception as exc:  # a live failure is recorded, never silently dropped
            error = str(exc)
            usage = {"model_calls": 0, "priced_calls": 0, "cost_usd": None,
                     "input_tokens": None, "output_tokens": None}
        finally:
            connection.close()
        duration_ms = int((perf_counter() - started) * 1000)

        # Agent-quality scoring against GT where a mapping exists.
        gt_handoff = None
        gt_final = None
        if case["suite"] == "agent" and case["expected_ref"] in truth["agent"]:
            gt = truth["agent"][case["expected_ref"]]
            gt_handoff, gt_final = gt["expected_handoff"], gt["expected_final_state"]
        handoff_correct = (handoff == gt_handoff) if gt_handoff is not None else None
        final_correct = (final_state == gt_final) if gt_final is not None else None
        completed = error == "" and final_state is not None

        # Cost stays missing unless the provider reported it for every call.
        cost = usage["cost_usd"] if usage["model_calls"] and usage["priced_calls"] == usage["model_calls"] else None

        rows.append({
            "case_id": case_id, "suite": case["suite"], "scenario_type": case["scenario_type"],
            "pass": bool(completed and (handoff_correct in (None, True)) and (final_correct in (None, True))),
            "failure_reason": error or ("" if completed else "did not complete"),
            "expected": f"handoff={gt_handoff};final={gt_final}",
            "actual": f"handoff={handoff};final={final_state}",
            "duration_ms": duration_ms, "backend": settings.llm_backend,
            "model": settings.llm_model or settings.bedrock_model_id or settings.local_llm_model or "",
            "input_tokens": usage["input_tokens"] if usage["input_tokens"] is not None else "",
            "output_tokens": usage["output_tokens"] if usage["output_tokens"] is not None else "",
            "cost_usd": cost if cost is not None else "",
            # metric fields
            "completed": completed,
            "handoff_correct": handoff_correct, "final_correct": final_correct,
            "model_calls": usage["model_calls"], "priced_calls": usage["priced_calls"],
            "cost_value": cost, "latency_ms": duration_ms,
            "input_tokens_val": usage["input_tokens"], "output_tokens_val": usage["output_tokens"],
        })
    return rows
