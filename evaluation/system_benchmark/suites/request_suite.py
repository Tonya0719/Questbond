"""Request understanding / clarification suite (offline, deterministic mock intake).

Runs the product intake structuring + conservative triage on fixed request text
and compares structured fields, readiness, clarification and human-review routing
against ground truth. Ground truth is only read here for comparison.
"""
from __future__ import annotations

from time import perf_counter

from src.intake import IntakeAgent
from src.services.triage_service import assess_request
from src.validators import check_request_ready

from .. import loaders


def _clarification_token(ready, human_review, structured) -> str:
    if human_review:
        return "coordinator review"
    if ready:
        return "none"
    if not structured["service_rule_id"]:
        return "ask service type"
    if not structured["window_start"] or not structured["window_end"]:
        return "ask appointment window"
    if not structured["zone"]:
        return "ask location"
    return "ask appointment window"


def run(cases: list[dict], truth: dict[str, dict]) -> list[dict]:
    gt = truth["request"]
    rows = []
    for case in [c for c in cases if c["suite"] == "request"]:
        case_id = case["case_id"]
        expected = gt[case["expected_ref"]]
        started = perf_counter()
        # Each request gets an isolated world so cases never interfere.
        connection = loaders.new_world()
        try:
            connection.execute("INSERT INTO customer_requests VALUES (?,?,?,?,?,?)",
                               (case_id, "NEW", "2030-03-01T00:00", "WEB", expected["input_text"], "en"))
            connection.commit()
            IntakeAgent().structure_request(connection, case_id)
            structured = dict(connection.execute(
                "SELECT * FROM structured_requests WHERE request_id=?", (case_id,)).fetchone())
            triage = assess_request(expected["input_text"])
        finally:
            connection.close()
        duration_ms = int((perf_counter() - started) * 1000)

        ready, _missing = check_request_ready(structured)
        actual_ready = bool(ready)
        actual_human_review = bool(triage["human_review_required"])
        actual_clarification = _clarification_token(actual_ready, actual_human_review, structured)

        exp_rule = expected["expected_service_rule"] or None
        exp_zone = expected["expected_zone"] or None
        exp_ws = expected["expected_window_start"] or None
        exp_we = expected["expected_window_end"] or None
        exp_ready = expected["expected_ready"].strip().lower() == "true"
        exp_hr = expected["expected_human_review"].strip().lower() == "true"
        exp_clar = expected["expected_clarification"]

        service_rule_correct = (structured["service_rule_id"] or None) == exp_rule
        zone_correct = (structured["zone"] or None) == exp_zone
        window_correct = ((structured["window_start"] or None) == exp_ws
                          and (structured["window_end"] or None) == exp_we)
        readiness_correct = actual_ready == exp_ready
        clarification_correct = actual_clarification == exp_clar
        human_review_correct = actual_human_review == exp_hr

        missing_critical = not exp_ready and (exp_rule is None or exp_ws is None or exp_zone is None)
        # Fabrication: system invented a scheduling-critical field that GT says should be absent.
        fabricated = 0
        if missing_critical:
            if exp_rule is None and structured["service_rule_id"]:
                fabricated = 1
            if exp_ws is None and structured["window_start"]:
                fabricated = 1
            if exp_zone is None and structured["zone"]:
                fabricated = 1
        unsafe_auto_scheduled = 1 if (exp_hr and actual_ready and not actual_human_review) else 0

        passed = (service_rule_correct and zone_correct and window_correct
                  and readiness_correct and clarification_correct and human_review_correct)
        rows.append({
            "case_id": case_id, "suite": "request", "scenario_type": case["scenario_type"],
            "pass": passed,
            "failure_reason": "" if passed else _fail_reason(
                service_rule_correct, zone_correct, window_correct,
                readiness_correct, clarification_correct, human_review_correct),
            "expected": f"rule={exp_rule};zone={exp_zone};ready={exp_ready};clar={exp_clar};hr={exp_hr}",
            "actual": f"rule={structured['service_rule_id']};zone={structured['zone']};"
                      f"ready={actual_ready};clar={actual_clarification};hr={actual_human_review}",
            "duration_ms": duration_ms, "backend": "mock", "model": "",
            "input_tokens": "", "output_tokens": "", "cost_usd": "",
            # metric fields
            "has_service_rule_gt": exp_rule is not None, "service_rule_correct": service_rule_correct,
            "has_zone_gt": exp_zone is not None, "zone_correct": zone_correct,
            "has_window_gt": exp_ws is not None, "window_correct": window_correct,
            "readiness_correct": readiness_correct, "clarification_correct": clarification_correct,
            "human_review_correct": human_review_correct,
            "expected_human_review": exp_hr, "missing_scheduling_critical": missing_critical,
            "fabricated": fabricated, "unsafe_auto_scheduled": unsafe_auto_scheduled,
        })
    return rows


def _fail_reason(rule, zone, window, ready, clar, hr) -> str:
    parts = []
    if not rule:
        parts.append("service_rule")
    if not zone:
        parts.append("zone")
    if not window:
        parts.append("window")
    if not ready:
        parts.append("readiness")
    if not clar:
        parts.append("clarification")
    if not hr:
        parts.append("human_review")
    return "mismatch: " + ",".join(parts)
