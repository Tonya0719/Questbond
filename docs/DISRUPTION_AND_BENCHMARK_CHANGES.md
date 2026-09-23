# Disruption Recovery + System Benchmark — Change Summary

This branch adds generalized technician-disruption recovery (UNAVAILABLE + DELAYED)
across the deterministic backend, the two-agent orchestration, and both staff UIs,
plus a separate quantitative system benchmark. No third agent was introduced and the
Week 1 booking flow is unchanged.

## 1. Disruption recovery (deterministic backend)

`src/services/disruption_service.py`
- Generalized the sick-leave flow into `create_recovery_plan(..., event_type, reason)`.
  `create_sick_leave_plan` is kept as a backwards-compatible wrapper (UNAVAILABLE).
- Added `create_delay_plan(...)` that normalizes a DELAYED report
  (`effective_from` + `delay_minutes`) onto the existing interval schema.
- DELAYED applies a minimum-change rule: only jobs whose feasibility is actually
  broken are reconsidered; the same technician is kept and shifted when possible
  (`SHIFT_SAME_TECHNICIAN`), otherwise a qualified replacement, otherwise `UNRESOLVED`.
- One active disruption per technician at a time.
- Governance fields per action: `technician_changed`, `time_changed`,
  `customer_appointment_changed`, `requires_human_approval`, `approval_reasons`,
  before/after technician/start/end, `booking_status`.
- Frozen no-partial-apply: any `UNRESOLVED` action blocks the whole plan.
- Added `reject_plan(...)` (zero schedule mutation) and `recalculate_plan(...)`.
- Approval keeps `BEGIN IMMEDIATE` revalidation, stale detection and idempotency;
  customer notices remain drafts (no email is sent).

No database redesign: reuses `operational_events` / `reschedule_plans` /
`reschedule_actions` / `customer_notifications`.

## 2. Agent integration (no third agent)

- `src/database.py`: additive `disruption_sessions(session_id, event_id)` mapping table.
- `src/tools/disruption_tools.py`: three read/propose tools, scheduling-agent only —
  `get_disruption_context`, `propose_recovery`, `get_recovery_plan`.
  Approve/reject/apply are never exposed as LLM tools.
- `src/tools/executor.py`: additive event-scope check for `event_id` args; existing
  request/customer/assignment ownership checks are unchanged.
- `src/tools/registry.py`: register the three tools + `EventIdInput`.
- `src/agents/scheduling_operations_agent.py`: `run_disruption_recovery` path
  (mock drives tools directly; live uses the tool loop).
- `src/agents/prompts.py`: `DISRUPTION_RECOVERY_PROMPT`.
- `src/orchestration/orchestrator.py`: `run_disruption_recovery` entry — deterministic
  event/plan first, zero-affected disruptions create no session, otherwise an
  event-anchored scheduling-agent session, routing to a `human_coordinator` handoff.

## 3. UI

- `src/ui/technician_view.py`: added a "Report disruption" area (UNAVAILABLE / DELAYED
  only). Technicians cannot pick replacements, approve/reject, or mutate confirmed
  schedules; a report only produces a proposal for coordinator review.
- `src/ui/coordinator_view.py`: upgraded the sick-leave prototype in place into a
  generalized "Recovery Plans" section supporting UNAVAILABLE + DELAYED, with the
  governance columns and Approve / Reject / Recalculate actions. The seed button is
  retained and labelled as a Demo / Developer tool.

## 4. Multimodal intake harness (tests only)

- `tests/test_multimodal_intake.py`: photo-only, text-only regression, text+photo
  current-policy regression, validation boundaries, raw-bytes-not-persisted, mock-vs-live.
- `evaluation/evaluate_photo_quality.py`: offline photo-quality scaffold; refuses to
  report accuracy on the mock backend; live requires `--allow-live`.

## 5. System benchmark (separate quantitative framework)

`evaluation/system_benchmark/` — 120 offline cases + a 45-case live subset.
- `config.py`, `loaders.py`, `metrics.py`, `reporters.py`, `run.py`, `README.md`.
- `fixtures/base/`: fixed synthetic world (14 technicians, 24 customers, 34 jobs,
  30 schedules, 9 service rules) on a 2030-03-04/05 calendar.
- `cases.csv`: unified registry; `ground_truth/`: modular per-suite GT
  (request / scheduling / disruption / governance / agent); robustness expectations
  are inlined in `cases.csv`.
- `suites/`: request, scheduling, disruption, governance, agent, robustness runners
  plus the live runner.
- Modes: `--mode validate | offline | live`. Live requires an explicit `--yes` and
  refuses to run on the mock backend; it prints a pre-run report (cases/backend/model/
  estimated calls/output path).
- Benchmark ground truth is only read for comparison and never by runtime decision
  logic. Deterministic scheduling metrics are not credited to the LLM. Provider cost
  is used where reported; missing cost stays missing (never zero).

Run artifacts are written to `results/system_benchmark/` (gitignored).

## Test / benchmark status

Environment: `conda activate hackathon` (Python 3.13), `LLM_BACKEND=mock` for offline.

- Product tests: `python -m pytest tests -q` → 136 passed.
- Offline eval: `python evaluation/run_eval.py` → passed.
- Benchmark validate: `python -m evaluation.system_benchmark.run --mode validate` → passed.
- Benchmark offline: `python -m evaluation.system_benchmark.run --mode offline` → 120/120 cases pass.
  - Request: service-rule / readiness / clarification accuracy 100%, fabrication 0%.
  - Scheduling: feasible-schedule rate 100%, deterministic-assignment agreement 100%.
  - Disruption: affected-job precision/recall 100%, unnecessary-change rate 0%,
    recovery success 100%, correct-unresolved-detection 100%.
  - Governance: pre-approval / rejected-plan / unauthorized mutations = 0.
  - Robustness: safe-failure rate 100%.
- Benchmark live (gateway, Claude Sonnet 4.5, 45 cases): task completion 100%,
  handoff accuracy 80%, final-state accuracy 80%, p50 ~30s, p95 ~33s,
  avg input ~15k / output ~1.1k tokens; provider cost not reported by the gateway.
  Live results are separate from offline and were not reconciled into offline metrics.

Notes:
- Offline/mock results measure deterministic correctness and safety, not live language quality.
- Multimodal visual accuracy is a separate track and is not part of the system benchmark.
- The live model id must include the full version suffix
  (e.g. `global.anthropic.claude-sonnet-4-5-20250929-v1:0`); a truncated id returns HTTP 400.
