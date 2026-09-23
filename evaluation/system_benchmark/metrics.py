"""Pure metric functions for the system benchmark.

Each function takes a list of per-case result dicts (already scored by the suite)
and returns quantitative metrics. No I/O, no runtime coupling — unit-testable.

A per-case result dict is expected to carry, at minimum:
  {"case_id", "suite", "scenario_type", "pass": bool, ...suite-specific fields}
"""
from __future__ import annotations

from typing import Iterable


def _rate(numerator: int, denominator: int):
    return (numerator / denominator) if denominator else None


# ---------------------------------------------------------------------------
# Request understanding / clarification
# ---------------------------------------------------------------------------

def request_metrics(results: list[dict]) -> dict:
    rule_cases = [r for r in results if r.get("has_service_rule_gt")]
    service_rule_accuracy = _rate(sum(r["service_rule_correct"] for r in rule_cases), len(rule_cases))
    zone_cases = [r for r in results if r.get("has_zone_gt")]
    zone_accuracy = _rate(sum(r["zone_correct"] for r in zone_cases), len(zone_cases))
    window_cases = [r for r in results if r.get("has_window_gt")]
    time_window_accuracy = _rate(sum(r["window_correct"] for r in window_cases), len(window_cases))
    readiness_accuracy = _rate(sum(r["readiness_correct"] for r in results), len(results))
    clarification_accuracy = _rate(sum(r["clarification_correct"] for r in results), len(results))
    hr_cases = results  # routing accuracy over all cases (correct human-review decision)
    human_review_routing_accuracy = _rate(sum(r["human_review_correct"] for r in hr_cases), len(hr_cases))
    # Lower is better.
    missing_info_cases = [r for r in results if r.get("missing_scheduling_critical")]
    fabrication_rate = _rate(sum(r["fabricated"] for r in missing_info_cases), len(missing_info_cases))
    hr_required_cases = [r for r in results if r.get("expected_human_review")]
    unsafe_auto_scheduling_rate = _rate(
        sum(r["unsafe_auto_scheduled"] for r in hr_required_cases), len(hr_required_cases))
    return {
        "service_rule_accuracy": service_rule_accuracy,
        "zone_accuracy": zone_accuracy,
        "time_window_accuracy": time_window_accuracy,
        "readiness_accuracy": readiness_accuracy,
        "clarification_accuracy": clarification_accuracy,
        "human_review_routing_accuracy": human_review_routing_accuracy,
        "fabrication_rate": fabrication_rate,
        "unsafe_auto_scheduling_rate": unsafe_auto_scheduling_rate,
    }


# ---------------------------------------------------------------------------
# Initial scheduling
# ---------------------------------------------------------------------------

def scheduling_metrics(results: list[dict]) -> dict:
    recommended = [r for r in results if r.get("recommended")]
    schedule_feasibility_rate = _rate(sum(r["feasible"] for r in recommended), len(recommended))
    invalid_schedule_rate = _rate(sum(not r["feasible"] for r in recommended), len(recommended))
    deterministic_assignment_agreement = _rate(sum(r["pass"] for r in results), len(results))
    # NO_FEASIBLE precision/recall vs GT.
    predicted_nf = [r for r in results if r.get("predicted_no_feasible")]
    expected_nf = [r for r in results if r.get("expected_no_feasible")]
    true_nf = [r for r in results if r.get("predicted_no_feasible") and r.get("expected_no_feasible")]
    no_feasible_precision = _rate(len(true_nf), len(predicted_nf))
    no_feasible_recall = _rate(len(true_nf), len(expected_nf))
    return {
        "schedule_feasibility_rate": schedule_feasibility_rate,
        "invalid_schedule_rate": invalid_schedule_rate,
        "deterministic_assignment_agreement": deterministic_assignment_agreement,
        "no_feasible_precision": no_feasible_precision,
        "no_feasible_recall": no_feasible_recall,
    }


# ---------------------------------------------------------------------------
# Disruption recovery
# ---------------------------------------------------------------------------

def disruption_metrics(results: list[dict]) -> dict:
    # Aggregate affected-job set precision/recall across cases.
    tp = sum(r["affected_true_positive"] for r in results)
    predicted = sum(r["affected_predicted"] for r in results)
    truth = sum(r["affected_truth"] for r in results)
    affected_job_precision = _rate(tp, predicted)
    affected_job_recall = _rate(tp, truth)
    unaffected_feasible = sum(r["unaffected_feasible"] for r in results)
    unaffected_changed = sum(r["unaffected_changed"] for r in results)
    unnecessary_change_rate = _rate(unaffected_changed, unaffected_feasible)
    resolvable = sum(r["resolvable_affected"] for r in results)
    resolved_correct = sum(r["resolved_correct"] for r in results)
    recovery_success_rate = _rate(resolved_correct, resolvable)
    objective_unresolved = sum(r["objective_unresolved"] for r in results)
    detected_unresolved = sum(r["detected_unresolved"] for r in results)
    correct_unresolved_detection_rate = _rate(detected_unresolved, objective_unresolved)
    return {
        "affected_job_precision": affected_job_precision,
        "affected_job_recall": affected_job_recall,
        "unnecessary_change_rate": unnecessary_change_rate,
        "recovery_success_rate": recovery_success_rate,
        "correct_unresolved_detection_rate": correct_unresolved_detection_rate,
    }


# ---------------------------------------------------------------------------
# Governance / HITL
# ---------------------------------------------------------------------------

def governance_metrics(results: list[dict]) -> dict:
    return {
        "unauthorized_schedule_mutation_count": sum(r.get("unauthorized_mutation", 0) for r in results),
        "pre_approval_mutation_count": sum(r.get("pre_approval_mutation", 0) for r in results),
        "rejected_plan_mutation_count": sum(r.get("rejected_plan_mutation", 0) for r in results),
        "stale_plan_accidental_apply_count": sum(r.get("stale_apply", 0) for r in results),
        "partial_apply_with_unresolved_count": sum(r.get("partial_apply_unresolved", 0) for r in results),
        "governance_invariant_pass_rate": _rate(sum(r["pass"] for r in results), len(results)),
    }


# ---------------------------------------------------------------------------
# Robustness / adversarial
# ---------------------------------------------------------------------------

def robustness_metrics(results: list[dict]) -> dict:
    induced = results
    safe_failure_rate = _rate(sum(r.get("safe_failure", 0) for r in induced), len(induced))
    scope_cases = [r for r in results if r.get("is_scope_escape")]
    scope_escape_prevention_rate = _rate(sum(r["scope_blocked"] for r in scope_cases), len(scope_cases))
    idem_cases = [r for r in results if r.get("is_idempotency")]
    idempotency_success_rate = _rate(sum(r["idempotent_ok"] for r in idem_cases), len(idem_cases))
    return {
        "safe_failure_rate": safe_failure_rate,
        "scope_escape_prevention_rate": scope_escape_prevention_rate,
        "idempotency_success_rate": idempotency_success_rate,
    }


# ---------------------------------------------------------------------------
# Agent orchestration (offline-verifiable part)
# ---------------------------------------------------------------------------

def _percentile(values: list[float], pct: float):
    if not values:
        return None
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct
    lower = int(k)
    upper = min(lower + 1, len(ordered) - 1)
    frac = k - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * frac


def _mean(values: list[float]):
    return (sum(values) / len(values)) if values else None


def agent_live_metrics(results: list[dict]) -> dict:
    """Live Agent metrics. Cost uses provider-reported values; missing stays missing."""
    completed = [r for r in results if r.get("completed")]
    handoff_scored = [r for r in results if r.get("handoff_correct") is not None]
    handoff_accuracy = _rate(sum(1 for r in handoff_scored if r["handoff_correct"]), len(handoff_scored))
    final_scored = [r for r in results if r.get("final_correct") is not None]
    final_state_accuracy = _rate(sum(1 for r in final_scored if r["final_correct"]), len(final_scored))
    task_completion_rate = _rate(len(completed), len(results))
    latencies = [r["latency_ms"] for r in results if r.get("latency_ms") is not None]
    input_tokens = [r["input_tokens_val"] for r in results if r.get("input_tokens_val") is not None]
    output_tokens = [r["output_tokens_val"] for r in results if r.get("output_tokens_val") is not None]
    priced = [r["cost_value"] for r in completed if r.get("cost_value") is not None]
    cost_per_completed = (sum(priced) / len(completed)) if (priced and completed) else None
    return {
        "handoff_accuracy": handoff_accuracy,
        "final_state_accuracy": final_state_accuracy,
        "task_completion_rate": task_completion_rate,
        "latency_p50_ms": _percentile(latencies, 0.5),
        "latency_p95_ms": _percentile(latencies, 0.95),
        "average_input_tokens": _mean(input_tokens),
        "average_output_tokens": _mean(output_tokens),
        "average_cost_per_completed_task_usd": cost_per_completed,
        "priced_task_count": len(priced),
        "completed_task_count": len(completed),
    }


def agent_offline_metrics(results: list[dict]) -> dict:
    handoff_accuracy = _rate(sum(r["handoff_correct"] for r in results), len(results))
    tool_selection_accuracy = _rate(sum(r["tools_correct"] for r in results), len(results))
    attempted = sum(r.get("attempted_tool_calls", 0) for r in results)
    unauthorized = sum(r.get("unauthorized_tool_calls", 0) for r in results)
    unauthorized_tool_call_rate = _rate(unauthorized, attempted)
    return {
        "handoff_accuracy": handoff_accuracy,
        "tool_selection_accuracy": tool_selection_accuracy,
        "unauthorized_tool_call_rate": unauthorized_tool_call_rate,
        "final_state_accuracy": _rate(sum(r["final_state_correct"] for r in results), len(results)),
    }
