from __future__ import annotations

import json
from datetime import datetime, time

from ..scheduling.assignment_engine import assign_technician
from ..scheduling.conflicts import has_schedule_conflict
from ..scheduling.eligibility import has_required_certifications, has_required_skills
from ..scheduling.workload import get_assigned_workload


def recommend_assignment(connection, request_id: str) -> dict:
    return assign_technician(request_id, connection).model_dump()


def validate_assignment_recommendation(connection, assignment_id: str) -> dict:
    assignment = connection.execute("SELECT * FROM assignment_results WHERE assignment_id=?", (assignment_id,)).fetchone()
    if not assignment:
        raise ValueError(f"Unknown assignment_id: {assignment_id}")
    if assignment["decision_status"] != "ASSIGNED":
        return {"assignment_id": assignment_id, "valid": True, "violations": [],
                "note": f"No assigned candidate for {assignment['decision_status']}"}
    request = connection.execute("SELECT * FROM structured_requests WHERE request_id=?", (assignment["request_id"],)).fetchone()
    technician = connection.execute("SELECT * FROM technicians WHERE technician_id=?", (assignment["technician_id"],)).fetchone()
    rule = connection.execute("SELECT * FROM service_rules WHERE service_rule_id=?", (request["service_rule_id"],)).fetchone()
    start, end = datetime.fromisoformat(assignment["scheduled_start"]), datetime.fromisoformat(assignment["scheduled_end"])
    violations = []
    if not request["ready_for_scheduling"]:
        violations.append("REQUEST_NOT_READY")
    if not has_required_skills(technician, rule):
        violations.append("SKILL_MISMATCH")
    if not has_required_certifications(technician, rule):
        violations.append("CERTIFICATION_MISMATCH")
    if technician["status"] != "AVAILABLE":
        violations.append("STATUS_UNAVAILABLE")
    if not (datetime.fromisoformat(request["window_start"]) <= start and end <= datetime.fromisoformat(request["window_end"])):
        violations.append("OUTSIDE_CUSTOMER_WINDOW")
    if not (time.fromisoformat(technician["shift_start"]) <= start.time() and end.time() <= time.fromisoformat(technician["shift_end"])):
        violations.append("OUTSIDE_SHIFT")
    if has_schedule_conflict(connection, technician["technician_id"], start, end):
        violations.append("SCHEDULE_CONFLICT")
    workload = get_assigned_workload(connection, technician["technician_id"], start.date().isoformat())
    if workload + request["estimated_duration_min"] > technician["max_workload_min"]:
        violations.append("WORKLOAD_LIMIT")
    reason = json.loads(assignment["recommendation_reason"])
    candidates = reason.get("eligible_candidates", [])
    if candidates:
        expected = min(candidates, key=lambda candidate: (
            candidate["projected_workload_ratio"], candidate["scheduled_start"], candidate["technician_id"]))
        if expected["technician_id"] != assignment["technician_id"] or expected["scheduled_start"] != assignment["scheduled_start"]:
            violations.append("RANKING_MISMATCH")
    return {"assignment_id": assignment_id, "valid": not violations, "violations": violations}


def get_assignment_decision_trace(connection, assignment_id: str) -> dict:
    assignment = connection.execute("SELECT * FROM assignment_results WHERE assignment_id=?", (assignment_id,)).fetchone()
    if not assignment:
        raise ValueError(f"Unknown assignment_id: {assignment_id}")
    reason = json.loads(assignment["recommendation_reason"])
    return {"assignment_id": assignment_id, "request_id": assignment["request_id"],
            "decision_status": assignment["decision_status"], "selected_candidate": {
                "technician_id": assignment["technician_id"], "scheduled_start": assignment["scheduled_start"],
                "scheduled_end": assignment["scheduled_end"], "workload_before": assignment["workload_before"],
                "workload_after": assignment["workload_after"],
                "projected_workload_ratio": reason.get("projected_workload_ratio")},
            "eligible_candidates": reason.get("eligible_candidates", []),
            "excluded_candidates": reason.get("excluded_technicians", {}),
            "ranking_rule": ["projected_workload_ratio", "scheduled_start", "technician_id"]}
