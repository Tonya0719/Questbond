"""Disruption recovery suite (offline, deterministic engine).

Runs the deterministic recovery engine (UNAVAILABLE via create_recovery_plan,
DELAYED via create_delay_plan) and compares the affected/changed/unresolved job
sets and approval requirement against ground truth. Also derives affected-job
precision/recall and the unnecessary-change rate that shows minimum-change behaviour.
"""
from __future__ import annotations

import json
from time import perf_counter

from src.services.disruption_service import (
    ACTION_UNRESOLVED,
    create_delay_plan,
    create_recovery_plan,
)

from .. import loaders

BENCH_DAY = "2030-03-04"


def _confirmed_jobs_of(connection, technician_id, day):
    return {row["job_id"] for row in connection.execute(
        """SELECT s.job_id FROM schedules s JOIN jobs j ON j.job_id=s.job_id
           WHERE s.technician_id=? AND s.assignment_status IN ('ASSIGNED','CONFIRMED')
             AND j.status IN ('SCHEDULED','IN_PROGRESS') AND substr(s.scheduled_start,1,10)=?""",
        (technician_id, day))}


def run(cases: list[dict], truth: dict[str, dict]) -> list[dict]:
    gt = truth["disruption"]
    rows = []
    for case in [c for c in cases if c["suite"] == "disruption"]:
        case_id = case["case_id"]
        expected = gt[case["expected_ref"]]
        event_type = expected["event_type"]
        technician_id = expected["technician_id"]
        started = perf_counter()
        connection = loaders.new_world()
        try:
            day_before = _confirmed_jobs_of(connection, technician_id, BENCH_DAY)
            if event_type == "UNAVAILABLE":
                plan = create_recovery_plan(connection, technician_id,
                                            expected["param_from"], expected["param_until_or_delay"],
                                            event_type="UNAVAILABLE", reason="benchmark unavailable")
            else:
                plan = create_delay_plan(connection, technician_id, expected["param_from"],
                                         int(expected["param_until_or_delay"]), reason="benchmark delay")
        finally:
            connection.close()
        duration_ms = int((perf_counter() - started) * 1000)

        actions = plan["actions"]
        actual_affected = {a["job_id"] for a in actions}
        actual_changed = {a["job_id"] for a in actions if a["technician_changed"] or a["time_changed"]}
        actual_unresolved = {a["job_id"] for a in actions if a["action_type"] == ACTION_UNRESOLVED}
        actual_requires_approval = bool(plan["plan"].get("requires_human_approval"))

        exp_affected = set(json.loads(expected["expected_affected_jobs"]))
        exp_changed = set(json.loads(expected["expected_changed_jobs"]))
        exp_unresolved = set(json.loads(expected["expected_unresolved_jobs"]))
        exp_requires_approval = expected["expected_requires_human_approval"].strip().lower() == "true"

        affected_ok = actual_affected == exp_affected
        changed_ok = actual_changed == exp_changed
        unresolved_ok = actual_unresolved == exp_unresolved
        approval_ok = actual_requires_approval == exp_requires_approval
        passed = affected_ok and changed_ok and unresolved_ok and approval_ok

        # Metric fields.
        tp = len(actual_affected & exp_affected)
        unaffected_feasible = len(day_before - exp_affected)
        unaffected_changed = len((actual_changed) - exp_affected)
        resolvable_affected = len(exp_affected - exp_unresolved)
        resolved_correct = len((actual_changed - actual_unresolved) & (exp_affected - exp_unresolved))
        objective_unresolved = len(exp_unresolved)
        detected_unresolved = len(actual_unresolved & exp_unresolved)

        rows.append({
            "case_id": case_id, "suite": "disruption", "scenario_type": case["scenario_type"],
            "pass": passed,
            "failure_reason": "" if passed else _fail(affected_ok, changed_ok, unresolved_ok, approval_ok),
            "expected": f"affected={sorted(exp_affected)};changed={sorted(exp_changed)};"
                        f"unresolved={sorted(exp_unresolved)};approval={exp_requires_approval}",
            "actual": f"affected={sorted(actual_affected)};changed={sorted(actual_changed)};"
                      f"unresolved={sorted(actual_unresolved)};approval={actual_requires_approval}",
            "duration_ms": duration_ms, "backend": "mock", "model": "",
            "input_tokens": "", "output_tokens": "", "cost_usd": "",
            # metric fields
            "affected_true_positive": tp, "affected_predicted": len(actual_affected),
            "affected_truth": len(exp_affected),
            "unaffected_feasible": unaffected_feasible, "unaffected_changed": unaffected_changed,
            "resolvable_affected": resolvable_affected, "resolved_correct": resolved_correct,
            "objective_unresolved": objective_unresolved, "detected_unresolved": detected_unresolved,
        })
    return rows


def _fail(affected, changed, unresolved, approval) -> str:
    parts = []
    if not affected:
        parts.append("affected_set")
    if not changed:
        parts.append("changed_set")
    if not unresolved:
        parts.append("unresolved_set")
    if not approval:
        parts.append("approval_flag")
    return "mismatch: " + ",".join(parts)
