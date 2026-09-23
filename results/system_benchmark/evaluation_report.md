# Questbond System Benchmark Report

- Benchmark version: 1.0.0
- Date: 2026-09-23
- Mode: offline
- Backend: mock (offline deterministic)

## Case counts

- request: 20/20 passed
- scheduling: 25/25 passed
- disruption: 30/30 passed
- governance: 15/15 passed
- agent: 15/15 passed
- robustness: 15/15 passed
- **total: 120 cases**

## Metrics

```json
{
  "request": {
    "service_rule_accuracy": 1.0,
    "zone_accuracy": 1.0,
    "time_window_accuracy": 1.0,
    "readiness_accuracy": 1.0,
    "clarification_accuracy": 1.0,
    "human_review_routing_accuracy": 1.0,
    "fabrication_rate": 0.0,
    "unsafe_auto_scheduling_rate": 0.0
  },
  "scheduling": {
    "schedule_feasibility_rate": 1.0,
    "invalid_schedule_rate": 0.0,
    "deterministic_assignment_agreement": 1.0,
    "no_feasible_precision": 1.0,
    "no_feasible_recall": 1.0
  },
  "disruption": {
    "affected_job_precision": 1.0,
    "affected_job_recall": 1.0,
    "unnecessary_change_rate": 0.0,
    "recovery_success_rate": 1.0,
    "correct_unresolved_detection_rate": 1.0
  },
  "governance": {
    "unauthorized_schedule_mutation_count": 0,
    "pre_approval_mutation_count": 0,
    "rejected_plan_mutation_count": 0,
    "stale_plan_accidental_apply_count": 0,
    "partial_apply_with_unresolved_count": 0,
    "governance_invariant_pass_rate": 1.0
  },
  "agent_offline": {
    "handoff_accuracy": 1.0,
    "tool_selection_accuracy": 1.0,
    "unauthorized_tool_call_rate": 0.0,
    "final_state_accuracy": 1.0
  },
  "robustness": {
    "safe_failure_rate": 1.0,
    "scope_escape_prevention_rate": 1.0,
    "idempotency_success_rate": 1.0
  }
}
```

## Failed cases

None — all cases passed.

## Limitations

- Offline/mock results measure deterministic correctness and safety, not live Agent language quality.
- Deterministic scheduling/recovery metrics are produced by Python, not the LLM.
- Live latency/tokens/cost are collected only in `--mode live` (separate artifacts).
- Multimodal visual accuracy is a separate evaluation track and is not included here.
