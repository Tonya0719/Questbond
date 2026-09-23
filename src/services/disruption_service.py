"""Deterministic disruption recovery with human-owned approval.

Supports two disruption types on the existing interval schema:

* ``UNAVAILABLE`` — the technician cannot work an interval at all
  (sick leave, emergency leave or any other absence recorded in ``reason``).
* ``DELAYED`` — the technician starts an interval late; only jobs whose
  feasibility is actually broken by the delay are reconsidered.

Scheduling and recovery truth stays deterministic in Python. Proposal
generation never mutates ``schedules``; ``approve``/``reject`` are the only
mutating operations and remain human-owned (never exposed as LLM tools).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from ..scheduling.conflicts import intervals_overlap
from ..scheduling.eligibility import eligibility_reasons
from ..scheduling.workload import get_assigned_workload, within_workload_capacity
from ..validators import ACTIVE_ASSIGNMENT_STATUSES, ACTIVE_JOB_STATUSES

# Disruption types normalised onto the existing operational_events interval schema.
SUPPORTED_EVENT_TYPES = {"UNAVAILABLE", "DELAYED"}
# Delay presets used by the demo technician UI; the service accepts any positive value.
DELAY_MINUTE_PRESETS = (30, 60, 90, 120)

# Action taxonomy exposed to the coordinator (governance contract, section 4).
ACTION_UNCHANGED = "UNCHANGED"
ACTION_REASSIGN_SAME_TIME = "REASSIGN_SAME_TIME"
ACTION_REASSIGN_AND_RESCHEDULE = "REASSIGN_AND_RESCHEDULE"
ACTION_SHIFT_SAME_TECHNICIAN = "SHIFT_SAME_TECHNICIAN"
ACTION_UNRESOLVED = "UNRESOLVED"

_OPEN_EVENT_STATUSES = ("OPEN", "RECOVERY_APPROVED")


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _affected_jobs(connection, technician_id: str, unavailable_from: str, unavailable_until: str):
    """Confirmed/active jobs of the technician that overlap the disruption interval."""
    return connection.execute(
        """SELECT s.*, j.customer_id, j.service_rule_id, j.priority, j.estimated_duration_min,
                  j.window_start, j.window_end, j.zone, sr.subtype
           FROM schedules s JOIN jobs j ON j.job_id=s.job_id
           JOIN service_rules sr ON sr.service_rule_id=j.service_rule_id
           WHERE s.technician_id=? AND s.assignment_status IN (?,?) AND j.status IN (?,?)
             AND s.scheduled_start < ? AND s.scheduled_end > ?
           ORDER BY CASE j.priority WHEN 'HIGH' THEN 0 ELSE 1 END, s.scheduled_start, s.job_id""",
        (technician_id, *sorted(ACTIVE_ASSIGNMENT_STATUSES), *sorted(ACTIVE_JOB_STATUSES),
         unavailable_until, unavailable_from),
    ).fetchall()


def _conflicts(connection, technician_id: str, start: datetime, end: datetime, ignored_jobs: set[str], reserved):
    unavailable = connection.execute(
        """SELECT unavailable_from, unavailable_until FROM operational_events
           WHERE technician_id=? AND event_status IN (?,?)""",
        (technician_id, *_OPEN_EVENT_STATUSES)).fetchall()
    if any(intervals_overlap(start, end, datetime.fromisoformat(row[0]), datetime.fromisoformat(row[1]))
           for row in unavailable):
        return True
    rows = connection.execute(
        """SELECT s.job_id, s.scheduled_start, s.scheduled_end FROM schedules s
           JOIN jobs j ON j.job_id=s.job_id WHERE s.technician_id=?
             AND s.assignment_status IN (?,?) AND j.status IN (?,?)""",
        (technician_id, *sorted(ACTIVE_ASSIGNMENT_STATUSES), *sorted(ACTIVE_JOB_STATUSES)),
    ).fetchall()
    if any(row['job_id'] not in ignored_jobs and intervals_overlap(
            start, end, datetime.fromisoformat(row['scheduled_start']), datetime.fromisoformat(row['scheduled_end']))
           for row in rows):
        return True
    return any(item[0] == technician_id and intervals_overlap(start, end, item[1], item[2]) for item in reserved)


def _bounds(connection, technician, job_date):
    """Feasible cursor bounds for a technician on a given day (shift ∩ operating hours)."""
    company = connection.execute("SELECT * FROM company_profile LIMIT 1").fetchone()
    shift_start = datetime.combine(job_date, datetime.strptime(technician['shift_start'], '%H:%M').time())
    shift_end = datetime.combine(job_date, datetime.strptime(technician['shift_end'], '%H:%M').time())
    operating_start = datetime.combine(job_date, datetime.strptime(company['operating_start'], '%H:%M').time())
    operating_end = datetime.combine(job_date, datetime.strptime(company['operating_end'], '%H:%M').time())
    return shift_start, shift_end, operating_start, operating_end


def _earliest_slot(connection, technician, job, ignored_jobs, reserved, not_before=None):
    """Earliest 30-minute-aligned feasible slot for ``technician`` inside the job window.

    ``not_before`` optionally forces the search to start at/after a datetime (used
    when a delayed technician must resume no earlier than the delay end).
    Returns ``(start, end)`` or ``None``.
    """
    original_start = datetime.fromisoformat(job['scheduled_start'])
    original_end = datetime.fromisoformat(job['scheduled_end'])
    window_start = datetime.fromisoformat(job['window_start'])
    window_end = datetime.fromisoformat(job['window_end'])
    duration = timedelta(minutes=job['estimated_duration_min'])
    shift_start, shift_end, operating_start, operating_end = _bounds(connection, technician, original_start.date())
    first = max(window_start, shift_start, operating_start)
    if not_before is not None:
        first = max(first, not_before)
    last = min(window_end, shift_end, operating_end)
    # Prefer the original time when it is still inside the feasible envelope.
    if not_before is None and first <= original_start and original_end <= last:
        cursor = original_start
    else:
        cursor = first
    cursor = cursor.replace(second=0, microsecond=0)
    if cursor.minute % 30:
        cursor += timedelta(minutes=30 - cursor.minute % 30)
    while cursor + duration <= last:
        end = cursor + duration
        if not _conflicts(connection, technician['technician_id'], cursor, end, ignored_jobs, reserved):
            return cursor, end
        cursor += timedelta(minutes=30)
    return None


def _replacement_options(connection, job, unavailable_technician: str, ignored_jobs, reserved):
    """Ranked replacement options among *other* technicians, preferring same time."""
    rule = connection.execute("SELECT * FROM service_rules WHERE service_rule_id=?", (job['service_rule_id'],)).fetchone()
    original_start = datetime.fromisoformat(job['scheduled_start'])
    options = []
    for tech in connection.execute("SELECT * FROM technicians WHERE technician_id<>? ORDER BY technician_id",
                                   (unavailable_technician,)):
        if eligibility_reasons(tech, rule):
            continue
        provisional = sum(int((item[2] - item[1]).total_seconds() // 60)
                          for item in reserved if item[0] == tech['technician_id'])
        workload = get_assigned_workload(connection, tech['technician_id'], original_start.date().isoformat()) + provisional
        if not within_workload_capacity(workload, job['estimated_duration_min'], tech['max_workload_min']):
            continue
        slot = _earliest_slot(connection, tech, job, ignored_jobs, reserved)
        if not slot:
            continue
        proposed_start, proposed_end = slot
        delay = max(0, int((proposed_start - original_start).total_seconds() // 60))
        same_time = proposed_start == original_start
        projected = (workload + job['estimated_duration_min']) / max(1, tech['max_workload_min'])
        options.append((0 if same_time else 1, delay, projected, tech['technician_id'],
                        proposed_start, proposed_end, workload))
    return sorted(options)


def _resolve_job(connection, job, disrupted_technician, event_type, delay_end, ignored_jobs, reserved):
    """Return a proposal tuple ``(job, tech, start_iso, end_iso, action_type, reason)``.

    DELAYED prefers keeping the same technician on a later slot (minimum change);
    both types fall back to a qualified replacement, else UNRESOLVED.
    """
    original_start = datetime.fromisoformat(job['scheduled_start'])

    if event_type == "DELAYED":
        technician = connection.execute("SELECT * FROM technicians WHERE technician_id=?",
                                        (disrupted_technician,)).fetchone()
        shifted = _earliest_slot(connection, technician, job, ignored_jobs, reserved, not_before=delay_end)
        if shifted:
            proposed_start, proposed_end = shifted
            reserved.append((disrupted_technician, proposed_start, proposed_end))
            delay = int((proposed_start - original_start).total_seconds() // 60)
            reason = (f"{disrupted_technician} stays assigned and shifts {delay} minutes later to "
                      f"absorb the delay while remaining inside the customer window.")
            return (job, disrupted_technician, proposed_start.isoformat(timespec='minutes'),
                    proposed_end.isoformat(timespec='minutes'), ACTION_SHIFT_SAME_TECHNICIAN, reason)

    options = _replacement_options(connection, job, disrupted_technician, ignored_jobs, reserved)
    if options:
        same_rank, delay, ratio, replacement, proposed_start, proposed_end, workload = options[0]
        reserved.append((replacement, proposed_start, proposed_end))
        action_type = ACTION_REASSIGN_SAME_TIME if same_rank == 0 else ACTION_REASSIGN_AND_RESCHEDULE
        reason = (f"{replacement} is qualified and conflict-free; "
                  f"{'the original time is preserved' if same_rank == 0 else f'the earliest feasible slot adds {delay} minutes'}; "
                  f"projected workload is {workload + job['estimated_duration_min']} minutes ({ratio:.0%}).")
        return (job, replacement, proposed_start.isoformat(timespec='minutes'),
                proposed_end.isoformat(timespec='minutes'), action_type, reason)

    return (job, None, None, None, ACTION_UNRESOLVED,
            'No qualified, available and conflict-free recovery exists inside the customer window.')


def _has_open_recovery(connection, technician_id: str):
    """Return an existing OPEN event with a still-PROPOSED plan, if any (one-at-a-time rule)."""
    return connection.execute(
        """SELECT oe.event_id, rp.plan_id FROM operational_events oe
           JOIN reschedule_plans rp ON rp.event_id=oe.event_id
           WHERE oe.technician_id=? AND oe.event_status='OPEN' AND rp.plan_status='PROPOSED'
           ORDER BY rp.created_at DESC LIMIT 1""",
        (technician_id,)).fetchone()


def create_recovery_plan(connection, technician_id: str, unavailable_from: str, unavailable_until: str,
                         event_type: str = "UNAVAILABLE", reason: str = "Technician unavailable") -> dict:
    """Create a deterministic recovery plan for a technician disruption.

    Idempotent for an identical (technician, event_type, interval); enforces the
    one-active-disruption-at-a-time rule; never mutates ``schedules``.
    """
    if event_type not in SUPPORTED_EVENT_TYPES:
        raise ValueError(f"Unsupported disruption type: {event_type}")
    start, end = datetime.fromisoformat(unavailable_from), datetime.fromisoformat(unavailable_until)
    if end <= start:
        raise ValueError("Disruption end must be after its start.")
    technician = connection.execute("SELECT * FROM technicians WHERE technician_id=?", (technician_id,)).fetchone()
    if not technician:
        raise ValueError("Unknown technician.")

    existing = connection.execute(
        """SELECT rp.plan_id FROM operational_events oe JOIN reschedule_plans rp ON rp.event_id=oe.event_id
           WHERE oe.technician_id=? AND oe.event_type=? AND oe.unavailable_from=?
             AND oe.unavailable_until=? ORDER BY rp.created_at DESC LIMIT 1""",
        (technician_id, event_type, unavailable_from, unavailable_until)).fetchone()
    if existing:
        return get_plan(connection, existing['plan_id'])

    open_recovery = _has_open_recovery(connection, technician_id)
    if open_recovery:
        raise ValueError("This technician already has an open recovery plan. "
                         "Approve, reject or recalculate it before creating another.")

    affected = _affected_jobs(connection, technician_id, unavailable_from, unavailable_until)
    delay_end = end if event_type == "DELAYED" else None

    event_id, plan_id, now = _id('EVT'), _id('PLAN'), _now()
    connection.execute("INSERT INTO operational_events VALUES (?,?,?,?,?,?,?,?)",
        (event_id, technician_id, event_type, unavailable_from, unavailable_until, reason, 'OPEN', now))

    # Minimum-change principle: only jobs that actually overlap the disruption are in
    # ``affected``; the rest of the technician's day is never regenerated.
    ignored_jobs = {row['job_id'] for row in affected}
    reserved, proposed = [], []
    for job in affected:
        proposed.append(_resolve_job(connection, job, technician_id, event_type, delay_end, ignored_jobs, reserved))

    resolved = sum(1 for item in proposed if item[4] not in (ACTION_UNRESOLVED,))
    unresolved = sum(1 for item in proposed if item[4] == ACTION_UNRESOLVED)
    connection.execute("INSERT INTO reschedule_plans VALUES (?,?,?,?,?,?,?,?,?)",
        (plan_id, event_id, 'PROPOSED', len(affected), resolved, unresolved, now, None, None))
    for job, tech, proposed_start, proposed_end, action_type, explanation in proposed:
        connection.execute("INSERT INTO reschedule_actions VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
            _id('ACT'), plan_id, job['job_id'], technician_id, tech,
            job['scheduled_start'], job['scheduled_end'], proposed_start, proposed_end, action_type, explanation))
    connection.commit()
    return get_plan(connection, plan_id)


def create_sick_leave_plan(connection, technician_id: str, unavailable_from: str,
                           unavailable_until: str, reason: str = "Technician reported sick") -> dict:
    """Backwards-compatible wrapper: sick leave is an UNAVAILABLE disruption."""
    return create_recovery_plan(connection, technician_id, unavailable_from, unavailable_until,
                                event_type="UNAVAILABLE", reason=reason)


def create_delay_plan(connection, technician_id: str, effective_from: str, delay_minutes: int,
                      reason: str = "Technician delayed") -> dict:
    """Normalise a DELAYED report onto the interval schema and build a recovery plan."""
    if delay_minutes <= 0:
        raise ValueError("Delay minutes must be positive.")
    start = datetime.fromisoformat(effective_from)
    until = (start + timedelta(minutes=delay_minutes)).isoformat(timespec='minutes')
    return create_recovery_plan(connection, technician_id, start.isoformat(timespec='minutes'), until,
                                event_type="DELAYED", reason=reason)


def _governance(action, booking_status: str) -> dict:
    """Deterministic approval-policy output for a single action (governance contract)."""
    technician_changed = bool(action['proposed_technician_id']
                              and action['proposed_technician_id'] != action['previous_technician_id'])
    booking_cancelled = action['action_type'] == ACTION_UNRESOLVED
    start_changed = bool(action['proposed_start'] and action['proposed_start'] != action['previous_start'])
    end_changed = bool(action['proposed_end'] and action['proposed_end'] != action['previous_end'])
    time_changed = start_changed or end_changed
    is_confirmed = booking_status == "CONFIRMED"
    customer_appointment_changed = is_confirmed and (technician_changed or time_changed or booking_cancelled)

    requires_human_approval = is_confirmed and (technician_changed or start_changed or end_changed or booking_cancelled)
    reasons = []
    if requires_human_approval:
        if technician_changed:
            reasons.append("CONFIRMED_TECHNICIAN_CHANGED")
        if start_changed:
            reasons.append("CONFIRMED_START_CHANGED")
        if end_changed:
            reasons.append("CONFIRMED_END_CHANGED")
        if booking_cancelled:
            reasons.append("CONFIRMED_BOOKING_CANCELLED")
    return {
        'technician_changed': technician_changed,
        'time_changed': time_changed,
        'customer_appointment_changed': customer_appointment_changed,
        'requires_human_approval': requires_human_approval,
        'approval_reasons': reasons,
    }


def _booking_status(connection, job_id: str) -> str:
    """CONFIRMED when the job has a confirmation record or a confirmed schedule row."""
    if connection.execute("SELECT 1 FROM booking_confirmations WHERE job_id=?", (job_id,)).fetchone():
        return "CONFIRMED"
    row = connection.execute("SELECT assignment_status FROM schedules WHERE job_id=?", (job_id,)).fetchone()
    if row and row['assignment_status'] == 'CONFIRMED':
        return "CONFIRMED"
    return "UNCONFIRMED"


def get_plan(connection, plan_id: str) -> dict:
    plan = connection.execute("""SELECT rp.*, oe.event_id, oe.technician_id, oe.event_type, oe.unavailable_from,
        oe.unavailable_until, oe.reason, oe.event_status, t.name_alias FROM reschedule_plans rp
        JOIN operational_events oe ON oe.event_id=rp.event_id
        JOIN technicians t ON t.technician_id=oe.technician_id WHERE rp.plan_id=?""", (plan_id,)).fetchone()
    if not plan:
        raise ValueError("Unknown recovery plan.")
    actions = connection.execute("""SELECT ra.*, j.priority, j.zone, sr.subtype,
        old.name_alias AS previous_technician, replacement.name_alias AS proposed_technician
        FROM reschedule_actions ra JOIN jobs j ON j.job_id=ra.job_id
        JOIN service_rules sr ON sr.service_rule_id=j.service_rule_id
        JOIN technicians old ON old.technician_id=ra.previous_technician_id
        LEFT JOIN technicians replacement ON replacement.technician_id=ra.proposed_technician_id
        WHERE ra.plan_id=? ORDER BY ra.previous_start, ra.job_id""", (plan_id,)).fetchall()
    enriched = []
    for row in actions:
        action = dict(row)
        booking_status = _booking_status(connection, action['job_id'])
        action['booking_status'] = booking_status
        # Governance contract field aliases (section 4).
        action['before_technician'] = action['previous_technician']
        action['before_start'] = action['previous_start']
        action['before_end'] = action['previous_end']
        action['after_technician'] = action['proposed_technician']
        action['after_start'] = action['proposed_start']
        action['after_end'] = action['proposed_end']
        action.update(_governance(action, booking_status))
        enriched.append(action)
    plan_dict = dict(plan)
    plan_dict['requires_human_approval'] = any(a['requires_human_approval'] for a in enriched)
    plan_dict['has_unresolved'] = any(a['action_type'] == ACTION_UNRESOLVED for a in enriched)
    return {'plan': plan_dict, 'actions': enriched}


def reject_plan(connection, plan_id: str, coordinator_id: str, reason: str = "") -> dict:
    """Record a rejection. Mutates zero schedule rows."""
    connection.execute("BEGIN IMMEDIATE")
    try:
        plan = connection.execute("SELECT * FROM reschedule_plans WHERE plan_id=?", (plan_id,)).fetchone()
        if not plan:
            raise ValueError("Unknown recovery plan.")
        if plan['plan_status'] == 'APPROVED':
            raise ValueError("An approved plan cannot be rejected.")
        if plan['plan_status'] == 'REJECTED':
            connection.commit()
            return get_plan(connection, plan_id)
        note = ("Rejected: " + reason.strip()) if reason.strip() else "Rejected by coordinator."
        connection.execute(
            "UPDATE reschedule_plans SET plan_status='REJECTED', approved_by=?, approved_at=? WHERE plan_id=?",
            (coordinator_id, _now(), plan_id))
        connection.execute("UPDATE operational_events SET event_status='RECOVERY_REJECTED', reason=? WHERE event_id=?",
                           (note, plan['event_id']))
        connection.commit()
        return get_plan(connection, plan_id)
    except Exception:
        connection.rollback()
        raise


def recalculate_plan(connection, plan_id: str) -> dict:
    """Discard a still-PROPOSED plan and rebuild it from current operational state.

    Used when a proposal is stale or the operational state changed. The disruption
    event is preserved; only the plan and its actions are regenerated.
    """
    plan = connection.execute("SELECT * FROM reschedule_plans WHERE plan_id=?", (plan_id,)).fetchone()
    if not plan:
        raise ValueError("Unknown recovery plan.")
    if plan['plan_status'] != 'PROPOSED':
        raise ValueError("Only a proposed plan can be recalculated.")
    event = connection.execute("SELECT * FROM operational_events WHERE event_id=?", (plan['event_id'],)).fetchone()
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute("DELETE FROM reschedule_actions WHERE plan_id=?", (plan_id,))
        connection.execute("DELETE FROM reschedule_plans WHERE plan_id=?", (plan_id,))
        connection.execute("DELETE FROM operational_events WHERE event_id=?", (plan['event_id'],))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return create_recovery_plan(connection, event['technician_id'], event['unavailable_from'],
                                event['unavailable_until'], event_type=event['event_type'], reason=event['reason'])


def approve_plan(connection, plan_id: str, coordinator_id: str) -> dict:
    """Human-owned approval. Applies only after full revalidation.

    Frozen unresolved policy: if any action is UNRESOLVED, the whole plan is
    routed to human review and NOTHING is auto-applied.
    """
    connection.execute("BEGIN IMMEDIATE")
    try:
        plan = connection.execute("SELECT * FROM reschedule_plans WHERE plan_id=?", (plan_id,)).fetchone()
        if not plan:
            raise ValueError("Unknown recovery plan.")
        if plan['plan_status'] == 'APPROVED':
            connection.commit()
            return get_plan(connection, plan_id)
        if plan['plan_status'] == 'REJECTED':
            raise ValueError("A rejected plan cannot be approved. Recalculate first.")
        actions = connection.execute("SELECT * FROM reschedule_actions WHERE plan_id=? ORDER BY previous_start", (plan_id,)).fetchall()
        if any(action['action_type'] == ACTION_UNRESOLVED for action in actions):
            raise ValueError("The plan has unresolved jobs and cannot be partially applied. "
                             "It requires human review.")
        ignored_jobs = {row['job_id'] for row in actions}
        reserved = []
        for action in actions:
            current = connection.execute("SELECT * FROM schedules WHERE job_id=?", (action['job_id'],)).fetchone()
            if (not current or current['technician_id'] != action['previous_technician_id']
                    or current['scheduled_start'] != action['previous_start']):
                raise ValueError("The schedule changed after planning. Recalculate before approval.")
            if action['action_type'] == ACTION_UNCHANGED:
                continue
            if action['proposed_technician_id']:
                start, end = datetime.fromisoformat(action['proposed_start']), datetime.fromisoformat(action['proposed_end'])
                if _conflicts(connection, action['proposed_technician_id'], start, end, ignored_jobs, reserved):
                    raise ValueError("A proposed slot now has a conflicting booking. Recalculate before approval.")
                reserved.append((action['proposed_technician_id'], start, end))
        now = _now()
        for action in actions:
            if action['action_type'] == ACTION_UNCHANGED or not action['proposed_technician_id']:
                continue
            # Skip a no-op write when nothing actually changed.
            if (action['proposed_technician_id'] == action['previous_technician_id']
                    and action['proposed_start'] == action['previous_start']
                    and action['proposed_end'] == action['previous_end']):
                continue
            connection.execute("UPDATE schedules SET technician_id=?, scheduled_start=?, scheduled_end=? WHERE job_id=?",
                (action['proposed_technician_id'], action['proposed_start'], action['proposed_end'], action['job_id']))
            details = connection.execute("""SELECT j.customer_id, bc.request_id, rc.email, c.name_alias,
                t.name_alias AS technician, sr.subtype FROM jobs j
                LEFT JOIN booking_confirmations bc ON bc.job_id=j.job_id
                LEFT JOIN request_contacts rc ON rc.request_id=bc.request_id
                JOIN customers c ON c.customer_id=j.customer_id
                JOIN technicians t ON t.technician_id=?
                JOIN service_rules sr ON sr.service_rule_id=j.service_rule_id WHERE j.job_id=?""",
                (action['proposed_technician_id'], action['job_id'])).fetchone()
            event_reason = connection.execute("SELECT reason FROM operational_events WHERE event_id=?",
                                              (plan['event_id'],)).fetchone()['reason']
            body = (f"Hello {details['name_alias']},\n\nYour {details['subtype']} appointment has been updated because "
                    f"the original technician was disrupted ({event_reason}). {details['technician']} is now scheduled from "
                    f"{action['proposed_start']} to {action['proposed_end']}.\n\nMendigo maintenance coordination")
            connection.execute("INSERT INTO customer_notifications VALUES (?,?,?,?,?,?,?,?,?)", (
                _id('NOTE'), details['request_id'], action['job_id'], 'DISRUPTION_RESCHEDULED',
                details['email'] or 'customer-contact-on-file', 'Maintenance appointment updated', body, 'DRAFT', now))
        connection.execute("UPDATE reschedule_plans SET plan_status='APPROVED', approved_by=?, approved_at=? WHERE plan_id=?",
                           (coordinator_id, now, plan_id))
        connection.execute("UPDATE operational_events SET event_status='RECOVERY_APPROVED' WHERE event_id=?", (plan['event_id'],))
        connection.commit()
        return get_plan(connection, plan_id)
    except Exception:
        connection.rollback()
        raise
