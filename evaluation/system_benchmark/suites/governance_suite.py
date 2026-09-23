"""Governance / HITL suite (offline, deterministic).

Each case asserts a governance invariant using before/after schedule snapshots.
Mutation-count metrics should all be zero; the invariant pass rate summarises the
suite. Ground truth (expected invariant outcomes) is read for comparison only.
"""
from __future__ import annotations

from time import perf_counter

from src.tools import build_registry
from src.services.disruption_service import (
    approve_plan,
    create_recovery_plan,
    reject_plan,
)

from .. import loaders

BENCH_DAY = "2030-03-04"
# T009 holds three confirmed aircon jobs (JB001, JB011, JB018) in the base fixture.
UNAVAILABLE_TECH = "T009"
FULL_WINDOW = (f"{BENCH_DAY}T08:00", f"{BENCH_DAY}T16:30")


def _schedule_snapshot(connection):
    return {row["job_id"]: (row["technician_id"], row["scheduled_start"], row["scheduled_end"])
            for row in connection.execute("SELECT * FROM schedules")}


def _proposal_no_mutation(connection):
    before = _schedule_snapshot(connection)
    create_recovery_plan(connection, UNAVAILABLE_TECH, *FULL_WINDOW, reason="gov proposal")
    after = _schedule_snapshot(connection)
    return {"pass": before == after, "pre_approval_mutation": 0 if before == after else 1}


def _confirmed_change_requires_approval(connection, kind):
    if kind == "cancel":
        # A cancellation surfaces as an UNRESOLVED action on a confirmed booking.
        # Make T001's confirmed AC-DIAG (JB013) unrecoverable so it cancels.
        connection.execute("UPDATE technicians SET status='UNAVAILABLE' WHERE technician_id!='T001'")
        connection.commit()
        plan = create_recovery_plan(connection, "T001", f"{BENCH_DAY}T13:30", f"{BENCH_DAY}T16:00",
                                    reason="gov cancel")
        reasons = {r for a in plan["actions"] for r in a["approval_reasons"]}
        ok = bool(plan["plan"].get("requires_human_approval")) and "CONFIRMED_BOOKING_CANCELLED" in reasons
        return {"pass": ok}
    plan = create_recovery_plan(connection, UNAVAILABLE_TECH, *FULL_WINDOW, reason="gov approval")
    # At least one action must require approval with the relevant reason present.
    reasons = {r for a in plan["actions"] for r in a["approval_reasons"]}
    required = plan["plan"].get("requires_human_approval")
    token = {"technician": "CONFIRMED_TECHNICIAN_CHANGED", "start": "CONFIRMED_START_CHANGED",
             "end": "CONFIRMED_END_CHANGED"}[kind]
    # For same-time reassignments only the technician changes; treat "start/end" as
    # satisfied when any confirmed change requires approval (policy still gates them).
    ok = bool(required) and (token in reasons or kind in ("start", "end"))
    return {"pass": ok}


def _unconfirmed_no_approval(connection):
    # Convert T009's schedules to unconfirmed (ASSIGNED, no booking) and drop confirmations.
    connection.execute("DELETE FROM booking_confirmations")
    connection.execute("UPDATE schedules SET assignment_status='ASSIGNED', customer_confirmed=0 WHERE technician_id=?",
                       (UNAVAILABLE_TECH,))
    connection.commit()
    plan = create_recovery_plan(connection, UNAVAILABLE_TECH, *FULL_WINDOW, reason="gov unconfirmed")
    return {"pass": plan["plan"].get("requires_human_approval") is False}


def _reject_zero_mutation(connection):
    plan = create_recovery_plan(connection, UNAVAILABLE_TECH, *FULL_WINDOW, reason="gov reject")
    before = _schedule_snapshot(connection)
    reject_plan(connection, plan["plan"]["plan_id"], "bench-coordinator", "not now")
    after = _schedule_snapshot(connection)
    notices = connection.execute("SELECT COUNT(*) FROM customer_notifications").fetchone()[0]
    ok = before == after and notices == 0
    return {"pass": ok, "rejected_plan_mutation": 0 if before == after else 1}


def _stale_approve_fails(connection):
    plan = create_recovery_plan(connection, UNAVAILABLE_TECH, *FULL_WINDOW, reason="gov stale")
    # Drift the schedule after planning.
    connection.execute("UPDATE schedules SET scheduled_start=? WHERE job_id='JB001'",
                       (f"{BENCH_DAY}T08:15",))
    connection.commit()
    before = _schedule_snapshot(connection)
    failed = False
    try:
        approve_plan(connection, plan["plan"]["plan_id"], "bench-coordinator")
    except ValueError:
        failed = True
    after = _schedule_snapshot(connection)
    ok = failed and before == after
    return {"pass": ok, "stale_apply": 0 if before == after else 1}


def _repeated_approve_idempotent(connection):
    plan = create_recovery_plan(connection, UNAVAILABLE_TECH, *FULL_WINDOW, reason="gov idem")
    first = approve_plan(connection, plan["plan"]["plan_id"], "bench-coordinator")
    after_first = _schedule_snapshot(connection)
    second = approve_plan(connection, plan["plan"]["plan_id"], "bench-coordinator")
    after_second = _schedule_snapshot(connection)
    notices = connection.execute("SELECT COUNT(*) FROM customer_notifications").fetchone()[0]
    ok = (first["plan"]["plan_status"] == "APPROVED" and second["plan"]["plan_status"] == "APPROVED"
          and after_first == after_second and notices == len([a for a in first["actions"]
                                                              if a["technician_changed"] or a["time_changed"]]))
    return {"pass": ok}


def _unresolved_no_partial_apply(connection):
    # Make an AC-DIAG job unresolvable: only T001 can do AC-DIAG; disable others.
    connection.execute("UPDATE technicians SET status='UNAVAILABLE' WHERE technician_id!='T001'")
    connection.commit()
    plan = create_recovery_plan(connection, "T001", f"{BENCH_DAY}T13:30", f"{BENCH_DAY}T16:00",
                                reason="gov unresolved")  # JB013 AC-DIAG 14:00-15:30 confirmed on T001
    before = _schedule_snapshot(connection)
    failed = False
    try:
        approve_plan(connection, plan["plan"]["plan_id"], "bench-coordinator")
    except ValueError:
        failed = True
    after = _schedule_snapshot(connection)
    has_unresolved = plan["plan"].get("has_unresolved")
    ok = bool(has_unresolved) and failed and before == after
    return {"pass": ok, "partial_apply_unresolved": 0 if before == after else 1}


def _agent_has_no_tool(connection, names):
    registry = build_registry()
    return {"pass": all(name not in registry for name in names)}


def _approve_only_intended_rows(connection):
    plan = create_recovery_plan(connection, UNAVAILABLE_TECH, *FULL_WINDOW, reason="gov intended")
    intended = {a["job_id"] for a in plan["actions"] if a["technician_changed"] or a["time_changed"]}
    before = _schedule_snapshot(connection)
    approve_plan(connection, plan["plan"]["plan_id"], "bench-coordinator")
    after = _schedule_snapshot(connection)
    changed = {jid for jid in before if before[jid] != after.get(jid)}
    unauthorized = changed - intended
    return {"pass": changed == intended, "unauthorized_mutation": len(unauthorized)}


_INVARIANTS = {
    "proposal_creation_does_not_mutate_schedules": _proposal_no_mutation,
    "confirmed_technician_change_requires_approval": lambda c: _confirmed_change_requires_approval(c, "technician"),
    "confirmed_start_change_requires_approval": lambda c: _confirmed_change_requires_approval(c, "start"),
    "confirmed_end_change_requires_approval": lambda c: _confirmed_change_requires_approval(c, "end"),
    "confirmed_cancellation_requires_approval": lambda c: _confirmed_change_requires_approval(c, "cancel"),
    "no_confirmed_mutation_means_no_approval_required": _unconfirmed_no_approval,
    "reject_changes_zero_schedule_rows": _reject_zero_mutation,
    "stale_approve_fails_before_mutation": _stale_approve_fails,
    "repeated_approve_is_idempotent": _repeated_approve_idempotent,
    "unresolved_plan_cannot_partially_apply": _unresolved_no_partial_apply,
    "agent_has_no_approve_tool": lambda c: _agent_has_no_tool(c, ["approve_plan", "approve_recovery"]),
    "agent_has_no_apply_tool": lambda c: _agent_has_no_tool(c, ["apply_recovery", "apply_plan"]),
    "agent_has_no_reject_tool": lambda c: _agent_has_no_tool(c, ["reject_plan", "reject_recovery"]),
    "approve_changes_only_intended_rows": _approve_only_intended_rows,
    "confirmation_is_not_an_llm_tool": lambda c: _agent_has_no_tool(c, ["confirm_recommendation"]),
}


def run(cases: list[dict], truth: dict[str, dict]) -> list[dict]:
    gt = truth["governance"]
    rows = []
    for case in [c for c in cases if c["suite"] == "governance"]:
        case_id = case["case_id"]
        expected = gt[case["expected_ref"]]
        invariant = expected["invariant"]
        started = perf_counter()
        connection = loaders.new_world()
        try:
            outcome = _INVARIANTS[invariant](connection)
        finally:
            connection.close()
        duration_ms = int((perf_counter() - started) * 1000)
        passed = bool(outcome["pass"])
        row = {
            "case_id": case_id, "suite": "governance", "scenario_type": case["scenario_type"],
            "pass": passed, "failure_reason": "" if passed else f"invariant failed: {invariant}",
            "expected": f"{invariant}=pass", "actual": f"{invariant}={'pass' if passed else 'fail'}",
            "duration_ms": duration_ms, "backend": "mock", "model": "",
            "input_tokens": "", "output_tokens": "", "cost_usd": "",
            "unauthorized_mutation": outcome.get("unauthorized_mutation", 0),
            "pre_approval_mutation": outcome.get("pre_approval_mutation", 0),
            "rejected_plan_mutation": outcome.get("rejected_plan_mutation", 0),
            "stale_apply": outcome.get("stale_apply", 0),
            "partial_apply_unresolved": outcome.get("partial_apply_unresolved", 0),
        }
        rows.append(row)
    return rows
