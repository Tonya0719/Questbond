"""Checkpoint 1 — deterministic disruption backend (UNAVAILABLE + DELAYED).

These tests exercise the service layer only (no UI, no Agent). They build
precise, synthetic confirmed bookings so DELAYED minimum-change behaviour and
the governance/approval policy can be asserted deterministically.
"""
from datetime import date

import pytest

from src.demo_scenarios import seed_sick_leave_scenario
from src.services.disruption_service import (
    ACTION_REASSIGN_SAME_TIME,
    ACTION_SHIFT_SAME_TECHNICIAN,
    ACTION_UNRESOLVED,
    approve_plan,
    create_delay_plan,
    create_recovery_plan,
    create_sick_leave_plan,
    get_plan,
    recalculate_plan,
    reject_plan,
)

DAY = "2030-02-11"  # A fixed future weekday used across scenarios.


def _confirmed_job(connection, *, job_id, technician_id, service_rule_id, start, end,
                   window_start, window_end, priority="NORMAL", duration=60, confirmed=True):
    """Insert a confirmed booking (customer, job, schedule, optional confirmation)."""
    customer_id = f"CUST-{job_id}"
    request_id = f"REQ-{job_id}"
    assignment_id = f"ASG-{job_id}"
    connection.execute("INSERT OR IGNORE INTO customers VALUES (?,?,?,?,?,?,?)",
        (customer_id, f"Resident {job_id}", "RESIDENTIAL", "EMAIL", "01", "East", "any"))
    connection.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)", (
        job_id, customer_id, service_rule_id, priority, duration,
        f"{DAY}T{window_start}", f"{DAY}T{window_end}", "East", "SCHEDULED"))
    connection.execute("INSERT INTO schedules VALUES (?,?,?,?,?,?)", (
        job_id, technician_id, f"{DAY}T{start}", f"{DAY}T{end}", "CONFIRMED", 1))
    if confirmed:
        connection.execute("INSERT OR IGNORE INTO customer_requests VALUES (?,?,?,?,?,?)",
            (request_id, customer_id, f"{DAY}T00:00", "WEB", "seed", "en"))
        connection.execute("INSERT OR IGNORE INTO structured_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
            request_id, customer_id, service_rule_id, "Air-conditioning", "Service", "East", priority,
            f"{DAY}T{window_start}", f"{DAY}T{window_end}", duration, "[]", 1))
        connection.execute("INSERT OR IGNORE INTO request_contacts VALUES (?,?,?,?)",
            (request_id, f"Resident {job_id}", f"{job_id}@example.com", "Unit 01"))
        connection.execute("INSERT OR IGNORE INTO assignment_results VALUES (?,?,?,?,?,?,?,?,?,?)", (
            assignment_id, request_id, technician_id, f"{DAY}T{start}", f"{DAY}T{end}", "ASSIGNED", 0, duration,
            "{}", f"{DAY}T00:00"))
        connection.execute("INSERT INTO booking_confirmations VALUES (?,?,?,?,?)",
            (assignment_id, request_id, job_id, "demo-coordinator", f"{DAY}T00:00"))
    connection.commit()
    return job_id


# ----------------------------------------------------------------------------
# A. UNAVAILABLE — generalises the sick-leave flow
# ----------------------------------------------------------------------------

def test_unavailable_no_affected_jobs_records_plan_with_zero_actions(db):
    # T001 unavailable but has no confirmed jobs that day.
    plan = create_recovery_plan(db, "T001", f"{DAY}T08:30", f"{DAY}T12:00", event_type="UNAVAILABLE")
    assert plan['plan']['affected_job_count'] == 0
    assert plan['actions'] == []
    assert plan['plan']['requires_human_approval'] is False


def test_unavailable_same_time_replacement(db):
    # Alex (T001) booked; Blair (T002) and Casey (T003) qualified and free.
    _confirmed_job(db, job_id="J1", technician_id="T001", service_rule_id="AC-ROUTINE",
                   start="09:00", end="10:00", window_start="08:00", window_end="13:00")
    plan = create_sick_leave_plan(db, "T001", f"{DAY}T08:30", f"{DAY}T12:00")
    action = plan['actions'][0]
    assert action['action_type'] == ACTION_REASSIGN_SAME_TIME
    assert action['proposed_technician_id'] in {"T002", "T003"}
    assert action['proposed_start'] == f"{DAY}T09:00"
    assert action['technician_changed'] is True
    assert action['time_changed'] is False


def test_unavailable_no_feasible_replacement_is_unresolved(db):
    # A skill nobody else near this window has been made exclusive to T001:
    # remove other aircon techs' skills by making them UNAVAILABLE.
    db.execute("UPDATE technicians SET status='UNAVAILABLE' WHERE technician_id IN ('T002','T003')")
    db.commit()
    _confirmed_job(db, job_id="J1", technician_id="T001", service_rule_id="AC-DIAG",
                   start="09:00", end="10:30", window_start="08:00", window_end="11:00", duration=90)
    plan = create_sick_leave_plan(db, "T001", f"{DAY}T08:30", f"{DAY}T12:00")
    action = plan['actions'][0]
    assert action['action_type'] == ACTION_UNRESOLVED
    assert plan['plan']['unresolved_job_count'] == 1
    assert action['requires_human_approval'] is True
    assert "CONFIRMED_BOOKING_CANCELLED" in action['approval_reasons']


def test_unresolved_plan_cannot_be_partially_applied(db):
    db.execute("UPDATE technicians SET status='UNAVAILABLE' WHERE technician_id IN ('T002','T003')")
    db.commit()
    _confirmed_job(db, job_id="J1", technician_id="T001", service_rule_id="AC-DIAG",
                   start="09:00", end="10:30", window_start="08:00", window_end="11:00", duration=90)
    plan = create_sick_leave_plan(db, "T001", f"{DAY}T08:30", f"{DAY}T12:00")
    with pytest.raises(ValueError, match="unresolved"):
        approve_plan(db, plan['plan']['plan_id'], "coordinator-test")
    # Nothing changed.
    row = db.execute("SELECT technician_id FROM schedules WHERE job_id='J1'").fetchone()
    assert row['technician_id'] == "T001"


# ----------------------------------------------------------------------------
# B. DELAYED — minimum-change recovery
# ----------------------------------------------------------------------------

def test_delay_that_affects_no_job_leaves_everything_unchanged(db):
    # Job starts at 14:00; a 30-minute delay starting 09:00 ends at 09:30 and
    # does not overlap the job, so it is not even in the affected set.
    _confirmed_job(db, job_id="J1", technician_id="T001", service_rule_id="AC-ROUTINE",
                   start="14:00", end="15:00", window_start="08:00", window_end="17:00")
    plan = create_delay_plan(db, "T001", f"{DAY}T09:00", 30)
    assert plan['plan']['affected_job_count'] == 0
    assert plan['actions'] == []


def test_delay_downstream_job_still_feasible_same_technician_unchanged(db):
    # Job 09:00-10:00 in a wide window 08:00-13:00. A delay to 09:30 overlaps it,
    # but T001 can still shift to 09:30 within the window -> broken, shift same tech.
    _confirmed_job(db, job_id="J1", technician_id="T001", service_rule_id="AC-ROUTINE",
                   start="09:00", end="10:00", window_start="08:00", window_end="13:00")
    plan = create_delay_plan(db, "T001", f"{DAY}T09:00", 30)
    action = plan['actions'][0]
    assert action['action_type'] == ACTION_SHIFT_SAME_TECHNICIAN
    assert action['proposed_technician_id'] == "T001"
    assert action['proposed_start'] == f"{DAY}T09:30"
    assert action['technician_changed'] is False
    assert action['time_changed'] is True


def test_delay_that_ends_before_a_job_leaves_it_unchanged(db):
    # A later job that starts after the delay ends is never even in the affected
    # set: the delay cannot break a job it does not overlap.
    _confirmed_job(db, job_id="EARLY", technician_id="T001", service_rule_id="AC-ROUTINE",
                   start="08:00", end="08:30", window_start="08:00", window_end="13:00")
    _confirmed_job(db, job_id="LATER", technician_id="T001", service_rule_id="AC-ROUTINE",
                   start="11:00", end="12:00", window_start="08:00", window_end="13:00")
    # Delay overlaps EARLY (08:00-08:30) but ends 08:45; EARLY can shift, LATER untouched.
    plan = create_delay_plan(db, "T001", f"{DAY}T08:00", 45)
    assert plan['plan']['affected_job_count'] == 1  # Only EARLY overlaps the delay.
    job_ids = {a['job_id'] for a in plan['actions']}
    assert job_ids == {"EARLY"}  # LATER is not reconsidered (minimum change).


def test_delay_requires_replacement_when_no_shift_fits(db):
    # Narrow window 09:00-10:00 for a 60-min job; a 30-min delay makes T001 infeasible,
    # so a qualified replacement must take the original time.
    _confirmed_job(db, job_id="J1", technician_id="T001", service_rule_id="AC-ROUTINE",
                   start="09:00", end="10:00", window_start="09:00", window_end="10:00")
    plan = create_delay_plan(db, "T001", f"{DAY}T09:00", 30)
    action = plan['actions'][0]
    assert action['action_type'] == ACTION_REASSIGN_SAME_TIME
    assert action['proposed_technician_id'] in {"T002", "T003"}
    assert action['proposed_start'] == f"{DAY}T09:00"


def test_delay_no_feasible_recovery_is_unresolved(db):
    db.execute("UPDATE technicians SET status='UNAVAILABLE' WHERE technician_id IN ('T002','T003')")
    db.commit()
    _confirmed_job(db, job_id="J1", technician_id="T001", service_rule_id="AC-DIAG",
                   start="09:00", end="10:30", window_start="09:00", window_end="10:30", duration=90)
    plan = create_delay_plan(db, "T001", f"{DAY}T09:00", 60)
    assert plan['actions'][0]['action_type'] == ACTION_UNRESOLVED


def test_delay_plan_is_repeatable_and_idempotent(db):
    _confirmed_job(db, job_id="J1", technician_id="T001", service_rule_id="AC-ROUTINE",
                   start="09:00", end="10:00", window_start="08:00", window_end="13:00")
    first = create_delay_plan(db, "T001", f"{DAY}T09:00", 30)
    second = create_delay_plan(db, "T001", f"{DAY}T09:00", 30)
    assert first['plan']['plan_id'] == second['plan']['plan_id']
    assert db.execute("SELECT COUNT(*) FROM operational_events").fetchone()[0] == 1


# ----------------------------------------------------------------------------
# C. Governance / approval policy
# ----------------------------------------------------------------------------

def test_unconfirmed_booking_change_does_not_require_approval(db):
    # An unconfirmed job (no booking_confirmations, non-CONFIRMED schedule).
    customer_id = "CUST-U1"
    db.execute("INSERT INTO customers VALUES (?,?,?,?,?,?,?)",
        (customer_id, "Resident U1", "RESIDENTIAL", "EMAIL", "01", "East", "any"))
    db.execute("INSERT INTO jobs VALUES ('U1',?,?,?,?,?,?,?,?)",
        (customer_id, "AC-ROUTINE", "NORMAL", 60, f"{DAY}T08:00", f"{DAY}T13:00", "East", "SCHEDULED"))
    db.execute("INSERT INTO schedules VALUES ('U1','T001',?,?,?,?)",
        (f"{DAY}T09:00", f"{DAY}T10:00", "ASSIGNED", 0))
    db.commit()
    plan = create_sick_leave_plan(db, "T001", f"{DAY}T08:30", f"{DAY}T12:00")
    action = plan['actions'][0]
    assert action['booking_status'] == "UNCONFIRMED"
    assert action['requires_human_approval'] is False
    assert plan['plan']['requires_human_approval'] is False


def test_confirmed_technician_change_reports_approval_reason(db):
    _confirmed_job(db, job_id="J1", technician_id="T001", service_rule_id="AC-ROUTINE",
                   start="09:00", end="10:00", window_start="08:00", window_end="13:00")
    plan = create_sick_leave_plan(db, "T001", f"{DAY}T08:30", f"{DAY}T12:00")
    action = plan['actions'][0]
    assert action['requires_human_approval'] is True
    assert "CONFIRMED_TECHNICIAN_CHANGED" in action['approval_reasons']


# ----------------------------------------------------------------------------
# D. Human authority — approve / reject / stale / one-at-a-time
# ----------------------------------------------------------------------------

def test_proposal_creation_does_not_mutate_schedules(db):
    _confirmed_job(db, job_id="J1", technician_id="T001", service_rule_id="AC-ROUTINE",
                   start="09:00", end="10:00", window_start="08:00", window_end="13:00")
    create_sick_leave_plan(db, "T001", f"{DAY}T08:30", f"{DAY}T12:00")
    row = db.execute("SELECT technician_id, scheduled_start FROM schedules WHERE job_id='J1'").fetchone()
    assert row['technician_id'] == "T001"
    assert row['scheduled_start'] == f"{DAY}T09:00"


def test_reject_changes_zero_schedule_rows(db):
    _confirmed_job(db, job_id="J1", technician_id="T001", service_rule_id="AC-ROUTINE",
                   start="09:00", end="10:00", window_start="08:00", window_end="13:00")
    plan = create_sick_leave_plan(db, "T001", f"{DAY}T08:30", f"{DAY}T12:00")
    rejected = reject_plan(db, plan['plan']['plan_id'], "coordinator-test", "Prefer manual handling")
    assert rejected['plan']['plan_status'] == "REJECTED"
    row = db.execute("SELECT technician_id FROM schedules WHERE job_id='J1'").fetchone()
    assert row['technician_id'] == "T001"
    assert db.execute("SELECT COUNT(*) FROM customer_notifications").fetchone()[0] == 0


def test_rejected_plan_cannot_be_approved(db):
    _confirmed_job(db, job_id="J1", technician_id="T001", service_rule_id="AC-ROUTINE",
                   start="09:00", end="10:00", window_start="08:00", window_end="13:00")
    plan = create_sick_leave_plan(db, "T001", f"{DAY}T08:30", f"{DAY}T12:00")
    reject_plan(db, plan['plan']['plan_id'], "coordinator-test")
    with pytest.raises(ValueError, match="rejected"):
        approve_plan(db, plan['plan']['plan_id'], "coordinator-test")


def test_repeated_approval_is_idempotent(db):
    _confirmed_job(db, job_id="J1", technician_id="T001", service_rule_id="AC-ROUTINE",
                   start="09:00", end="10:00", window_start="08:00", window_end="13:00")
    plan = create_sick_leave_plan(db, "T001", f"{DAY}T08:30", f"{DAY}T12:00")
    first = approve_plan(db, plan['plan']['plan_id'], "coordinator-test")
    second = approve_plan(db, plan['plan']['plan_id'], "coordinator-test")
    assert first['plan']['plan_status'] == "APPROVED"
    assert second['plan']['plan_status'] == "APPROVED"
    assert db.execute("SELECT COUNT(*) FROM customer_notifications").fetchone()[0] == 1


def test_stale_proposal_fails_before_mutation(db):
    _confirmed_job(db, job_id="J1", technician_id="T001", service_rule_id="AC-ROUTINE",
                   start="09:00", end="10:00", window_start="08:00", window_end="13:00")
    plan = create_sick_leave_plan(db, "T001", f"{DAY}T08:30", f"{DAY}T12:00")
    # Operational state drifts after planning.
    db.execute("UPDATE schedules SET scheduled_start=? WHERE job_id='J1'", (f"{DAY}T09:30",))
    db.commit()
    with pytest.raises(ValueError, match="schedule changed"):
        approve_plan(db, plan['plan']['plan_id'], "coordinator-test")


def test_one_active_disruption_at_a_time(db):
    _confirmed_job(db, job_id="J1", technician_id="T001", service_rule_id="AC-ROUTINE",
                   start="09:00", end="10:00", window_start="08:00", window_end="13:00")
    create_sick_leave_plan(db, "T001", f"{DAY}T08:30", f"{DAY}T12:00")
    with pytest.raises(ValueError, match="open recovery plan"):
        create_delay_plan(db, "T001", f"{DAY}T14:00", 30)


def test_recalculate_rebuilds_a_proposed_plan(db):
    # AC-ROUTINE only needs the aircon_service skill; T002 (Blair) and T003 (Casey)
    # both qualify. Disable them first so the initial plan is UNRESOLVED.
    db.execute("UPDATE technicians SET status='UNAVAILABLE' WHERE technician_id IN ('T002','T003')")
    db.commit()
    _confirmed_job(db, job_id="J1", technician_id="T001", service_rule_id="AC-ROUTINE",
                   start="09:00", end="10:00", window_start="08:00", window_end="11:00")
    plan = create_sick_leave_plan(db, "T001", f"{DAY}T08:30", f"{DAY}T12:00")
    assert plan['actions'][0]['action_type'] == ACTION_UNRESOLVED
    # A qualified replacement becomes available; recalculation should now resolve it.
    db.execute("UPDATE technicians SET status='AVAILABLE' WHERE technician_id='T003'")
    db.commit()
    rebuilt = recalculate_plan(db, plan['plan']['plan_id'])
    assert rebuilt['actions'][0]['action_type'] == ACTION_REASSIGN_SAME_TIME
    assert rebuilt['actions'][0]['proposed_technician_id'] == "T003"
    assert db.execute("SELECT COUNT(*) FROM operational_events").fetchone()[0] == 1


# ----------------------------------------------------------------------------
# Backwards compatibility with the existing sick-leave demo scenario
# ----------------------------------------------------------------------------

def test_existing_sick_leave_demo_still_recovers_three_visits(db):
    scenario = seed_sick_leave_scenario(db, date(2030, 1, 20))
    recovery = create_sick_leave_plan(db, scenario['technician_id'],
                                      scenario['unavailable_from'], scenario['unavailable_until'])
    assert recovery['plan']['affected_job_count'] == 3
    assert recovery['plan']['resolved_job_count'] == 3
    assert all(a['action_type'] == ACTION_REASSIGN_SAME_TIME for a in recovery['actions'])
