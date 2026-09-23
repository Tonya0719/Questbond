"""Initial scheduling suite (offline, deterministic engine).

Builds a structured request directly and runs the deterministic assignment engine,
comparing status/technician/slot against ground truth. This measures deterministic
scheduling only and is never credited to the LLM. Ground truth is read for
comparison only.
"""
from __future__ import annotations

import json
from time import perf_counter

from src.scheduling.assignment_engine import assign_technician

from .. import loaders


def _prepare_request(connection, case_id, rule_id, zone, window_start, window_end):
    rule = connection.execute("SELECT * FROM service_rules WHERE service_rule_id=?", (rule_id,)).fetchone()
    duration = rule["default_duration_min"]
    connection.execute("INSERT INTO customer_requests VALUES (?,?,?,?,?,?)",
                       (case_id, "NEW", "2030-03-01T00:00", "WEB", "benchmark scheduling case", "en"))
    connection.execute("INSERT INTO structured_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
        case_id, None, rule_id, rule["category"], rule["subtype"], zone, rule["default_priority"],
        window_start, window_end, duration, "[]", 1))
    connection.commit()


def run(cases: list[dict], truth: dict[str, dict]) -> list[dict]:
    gt = truth["scheduling"]
    rows = []
    for case in [c for c in cases if c["suite"] == "scheduling"]:
        case_id = case["case_id"]
        expected = gt[case["expected_ref"]]
        started = perf_counter()
        connection = loaders.new_world()
        try:
            if expected["seed_variant"] == "empty":
                connection.execute("DELETE FROM schedules")
                connection.commit()
            _prepare_request(connection, case_id, expected["service_rule_id"], expected["zone"],
                             expected["window_start"], expected["window_end"])
            result = assign_technician(case_id, connection)
        finally:
            connection.close()
        duration_ms = int((perf_counter() - started) * 1000)

        exp_status = expected["expected_status"]
        exp_tech = expected["expected_technician_id"] or None
        exp_start = expected["expected_start"] or None
        exp_end = expected["expected_end"] or None

        actual_status = result.decision_status
        actual_tech = result.technician_id
        actual_start = result.scheduled_start
        actual_end = result.scheduled_end

        status_ok = actual_status == exp_status
        assignment_ok = (actual_tech == exp_tech and actual_start == exp_start and actual_end == exp_end)
        passed = status_ok and assignment_ok

        recommended = actual_status == "ASSIGNED"
        # A recommended schedule is "feasible" when the engine produced a slot within
        # the requested window (the engine already enforces all hard constraints).
        feasible = recommended and bool(actual_start and actual_end
                                        and actual_start >= expected["window_start"]
                                        and actual_end <= expected["window_end"])
        predicted_no_feasible = actual_status == "NO_FEASIBLE_TECHNICIAN"
        expected_no_feasible = exp_status == "NO_FEASIBLE_TECHNICIAN"

        rows.append({
            "case_id": case_id, "suite": "scheduling", "scenario_type": case["scenario_type"],
            "pass": passed,
            "failure_reason": "" if passed else (
                f"status {actual_status}!={exp_status}" if not status_ok
                else f"assignment {actual_tech}/{actual_start} != {exp_tech}/{exp_start}"),
            "expected": f"{exp_status}/{exp_tech}/{exp_start}-{exp_end}",
            "actual": f"{actual_status}/{actual_tech}/{actual_start}-{actual_end}",
            "duration_ms": duration_ms, "backend": "mock", "model": "",
            "input_tokens": "", "output_tokens": "", "cost_usd": "",
            # metric fields
            "recommended": recommended, "feasible": feasible,
            "predicted_no_feasible": predicted_no_feasible, "expected_no_feasible": expected_no_feasible,
        })
    return rows
