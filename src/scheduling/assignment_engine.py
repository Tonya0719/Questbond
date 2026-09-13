import json
from datetime import datetime, timezone
from uuid import uuid4

from ..config import settings
from ..database import connect
from ..schemas.assignment import AssignmentResult
from ..validators import check_request_ready
from .eligibility import eligibility_reasons
from .ranking import rank_candidates
from .slots import find_earliest_feasible_slot
from .workload import get_assigned_workload, within_workload_capacity


def _persist(connection, result: AssignmentResult):
    connection.execute(
        """INSERT INTO assignment_results VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (result.assignment_id, result.request_id, result.technician_id, result.scheduled_start,
         result.scheduled_end, result.decision_status, result.workload_before, result.workload_after,
         json.dumps(result.recommendation_reason, sort_keys=True), result.created_at),
    )
    connection.commit()


def assign_technician(request_id: str, connection=None) -> AssignmentResult:
    owns_connection = connection is None
    connection = connection or connect()
    try:
        request = connection.execute("SELECT * FROM structured_requests WHERE request_id=?", (request_id,)).fetchone()
        if request is None:
            raise ValueError(f"Unknown request_id: {request_id}")
        now = datetime.now(timezone.utc).isoformat()
        base = {"assignment_id": f"AR-{uuid4().hex[:12]}", "request_id": request_id, "created_at": now}
        ready, missing = check_request_ready(request)
        if not ready or not request["ready_for_scheduling"]:
            result = AssignmentResult(**base, decision_status="NEEDS_CLARIFICATION",
                recommendation_reason={"missing_fields": missing or json.loads(request["missing_fields"])})
            _persist(connection, result)
            return result
        rule = connection.execute("SELECT * FROM service_rules WHERE service_rule_id=?", (request["service_rule_id"],)).fetchone()
        if rule is None:
            result = AssignmentResult(**base, decision_status="NEEDS_CLARIFICATION",
                                      recommendation_reason={"missing_fields": ["service_rule_id"]})
            _persist(connection, result)
            return result
        company = connection.execute("SELECT * FROM company_profile LIMIT 1").fetchone()
        candidates, exclusions = [], {}
        for technician in connection.execute("SELECT * FROM technicians ORDER BY technician_id"):
            reasons = eligibility_reasons(technician, rule)
            if reasons:
                exclusions[technician["technician_id"]] = reasons
                continue
            workload = get_assigned_workload(connection, technician["technician_id"], request["window_start"][:10])
            duration = request["estimated_duration_min"]
            if not within_workload_capacity(workload, duration, technician["max_workload_min"]):
                exclusions[technician["technician_id"]] = ["WORKLOAD_LIMIT"]
                continue
            slot = find_earliest_feasible_slot(connection, technician, request["window_start"], request["window_end"],
                                               duration, company, settings.slot_granularity_min)
            if not slot:
                exclusions[technician["technician_id"]] = ["NO_FEASIBLE_SLOT"]
                continue
            candidates.append({"technician_id": technician["technician_id"],
                "scheduled_start": slot[0].isoformat(timespec="minutes"), "scheduled_end": slot[1].isoformat(timespec="minutes"),
                "workload_before": workload, "workload_after": workload + duration,
                "projected_workload_ratio": (workload + duration) / technician["max_workload_min"]})
        if not candidates:
            result = AssignmentResult(**base, decision_status="NO_FEASIBLE_TECHNICIAN",
                                      recommendation_reason={"excluded_technicians": exclusions})
        else:
            winner = rank_candidates(candidates)[0]
            reason = {"skill_match": True, "certification_match": True, "status": "AVAILABLE",
                      "schedule_conflict": False, "workload_before": winner["workload_before"],
                      "workload_after": winner["workload_after"],
                      "projected_workload_ratio": round(winner["projected_workload_ratio"], 6),
                      "ranking_reason": "lowest workload ratio, then earliest feasible start, then technician ID",
                      "eligible_candidates": candidates, "excluded_technicians": exclusions}
            result = AssignmentResult(**base, decision_status="ASSIGNED", recommendation_reason=reason, **winner)
        _persist(connection, result)
        return result
    finally:
        if owns_connection:
            connection.close()
