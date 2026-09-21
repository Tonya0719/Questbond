"""Deterministic sick-leave recovery with human-owned approval."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from ..scheduling.conflicts import intervals_overlap
from ..scheduling.eligibility import eligibility_reasons
from ..scheduling.workload import get_assigned_workload, within_workload_capacity
from ..validators import ACTIVE_ASSIGNMENT_STATUSES, ACTIVE_JOB_STATUSES


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _affected_jobs(connection, technician_id: str, unavailable_from: str, unavailable_until: str):
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
    unavailable = connection.execute("""SELECT unavailable_from, unavailable_until FROM operational_events
        WHERE technician_id=? AND event_status IN ('OPEN','RECOVERY_APPROVED')""", (technician_id,)).fetchall()
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


def _candidate_options(connection, job, unavailable_technician: str, ignored_jobs: set[str], reserved):
    rule = connection.execute("SELECT * FROM service_rules WHERE service_rule_id=?", (job['service_rule_id'],)).fetchone()
    company = connection.execute("SELECT * FROM company_profile LIMIT 1").fetchone()
    original_start, original_end = datetime.fromisoformat(job['scheduled_start']), datetime.fromisoformat(job['scheduled_end'])
    window_start, window_end = datetime.fromisoformat(job['window_start']), datetime.fromisoformat(job['window_end'])
    duration = timedelta(minutes=job['estimated_duration_min'])
    options = []
    for tech in connection.execute("SELECT * FROM technicians WHERE technician_id<>? ORDER BY technician_id", (unavailable_technician,)):
        if eligibility_reasons(tech, rule):
            continue
        provisional_minutes = sum(int((item[2] - item[1]).total_seconds() // 60)
                                  for item in reserved if item[0] == tech['technician_id'])
        workload = (get_assigned_workload(connection, tech['technician_id'], original_start.date().isoformat())
                    + provisional_minutes)
        if not within_workload_capacity(workload, job['estimated_duration_min'], tech['max_workload_min']):
            continue
        shift_start = datetime.combine(original_start.date(), datetime.strptime(tech['shift_start'], '%H:%M').time())
        shift_end = datetime.combine(original_start.date(), datetime.strptime(tech['shift_end'], '%H:%M').time())
        operating_start = datetime.combine(original_start.date(), datetime.strptime(company['operating_start'], '%H:%M').time())
        operating_end = datetime.combine(original_start.date(), datetime.strptime(company['operating_end'], '%H:%M').time())
        first = max(window_start, shift_start, operating_start)
        last = min(window_end, shift_end, operating_end)
        cursor = original_start if first <= original_start and original_end <= last else first
        cursor = cursor.replace(second=0, microsecond=0)
        if cursor.minute % 30:
            cursor += timedelta(minutes=30 - cursor.minute % 30)
        while cursor + duration <= last:
            end = cursor + duration
            if not _conflicts(connection, tech['technician_id'], cursor, end, ignored_jobs, reserved):
                delay = max(0, int((cursor - original_start).total_seconds() // 60))
                same_time = cursor == original_start
                projected = (workload + job['estimated_duration_min']) / max(1, tech['max_workload_min'])
                options.append((0 if same_time else 1, delay, projected, tech['technician_id'], cursor, end, workload))
                break
            cursor += timedelta(minutes=30)
    return sorted(options)


def create_sick_leave_plan(connection, technician_id: str, unavailable_from: str,
                           unavailable_until: str, reason: str = "Technician reported sick") -> dict:
    start, end = datetime.fromisoformat(unavailable_from), datetime.fromisoformat(unavailable_until)
    if end <= start:
        raise ValueError("Sick-leave end must be after its start.")
    technician = connection.execute("SELECT * FROM technicians WHERE technician_id=?", (technician_id,)).fetchone()
    if not technician:
        raise ValueError("Unknown technician.")
    existing = connection.execute(
        """SELECT rp.plan_id FROM operational_events oe JOIN reschedule_plans rp ON rp.event_id=oe.event_id
           WHERE oe.technician_id=? AND oe.event_type='SICK_LEAVE' AND oe.unavailable_from=?
             AND oe.unavailable_until=? ORDER BY rp.created_at DESC LIMIT 1""",
        (technician_id, unavailable_from, unavailable_until)).fetchone()
    if existing:
        return get_plan(connection, existing['plan_id'])
    affected = _affected_jobs(connection, technician_id, unavailable_from, unavailable_until)
    event_id, plan_id, now = _id('EVT'), _id('PLAN'), datetime.now(timezone.utc).isoformat()
    connection.execute("INSERT INTO operational_events VALUES (?,?,?,?,?,?,?,?)",
        (event_id, technician_id, 'SICK_LEAVE', unavailable_from, unavailable_until, reason, 'OPEN', now))
    ignored_jobs, reserved, proposed = {row['job_id'] for row in affected}, [], []
    for job in affected:
        options = _candidate_options(connection, job, technician_id, ignored_jobs, reserved)
        if options:
            same_rank, delay, ratio, replacement, proposed_start, proposed_end, workload = options[0]
            reserved.append((replacement, proposed_start, proposed_end))
            action_type = 'REASSIGN_SAME_TIME' if same_rank == 0 else 'REASSIGN_AND_RESCHEDULE'
            explanation = (f"{replacement} is qualified and conflict-free; "
                           f"{'the original time is preserved' if same_rank == 0 else f'the earliest feasible slot adds {delay} minutes'}; "
                           f"projected workload is {workload + job['estimated_duration_min']} minutes ({ratio:.0%}).")
            proposed.append((job, replacement, proposed_start.isoformat(timespec='minutes'),
                             proposed_end.isoformat(timespec='minutes'), action_type, explanation))
        else:
            proposed.append((job, None, None, None, 'UNRESOLVED',
                             'No qualified, available and conflict-free replacement exists inside the customer window.'))
    resolved = sum(item[1] is not None for item in proposed)
    connection.execute("INSERT INTO reschedule_plans VALUES (?,?,?,?,?,?,?,?,?)",
        (plan_id, event_id, 'PROPOSED', len(affected), resolved, len(affected) - resolved, now, None, None))
    for job, replacement, proposed_start, proposed_end, action_type, explanation in proposed:
        connection.execute("INSERT INTO reschedule_actions VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
            _id('ACT'), plan_id, job['job_id'], technician_id, replacement,
            job['scheduled_start'], job['scheduled_end'], proposed_start, proposed_end, action_type, explanation))
    connection.commit()
    return get_plan(connection, plan_id)


def get_plan(connection, plan_id: str) -> dict:
    plan = connection.execute("""SELECT rp.*, oe.technician_id, oe.event_type, oe.unavailable_from,
        oe.unavailable_until, oe.reason, t.name_alias FROM reschedule_plans rp
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
    return {'plan': dict(plan), 'actions': [dict(row) for row in actions]}


def approve_plan(connection, plan_id: str, coordinator_id: str) -> dict:
    connection.execute("BEGIN IMMEDIATE")
    try:
        plan = connection.execute("SELECT * FROM reschedule_plans WHERE plan_id=?", (plan_id,)).fetchone()
        if not plan:
            raise ValueError("Unknown recovery plan.")
        if plan['plan_status'] == 'APPROVED':
            connection.commit()
            return get_plan(connection, plan_id)
        actions = connection.execute("SELECT * FROM reschedule_actions WHERE plan_id=? ORDER BY previous_start", (plan_id,)).fetchall()
        ignored_jobs = {row['job_id'] for row in actions}
        reserved = []
        for action in actions:
            current = connection.execute("SELECT * FROM schedules WHERE job_id=?", (action['job_id'],)).fetchone()
            if not current or current['technician_id'] != action['previous_technician_id'] or current['scheduled_start'] != action['previous_start']:
                raise ValueError("The schedule changed after planning. Recalculate before approval.")
            if action['proposed_technician_id']:
                start, end = datetime.fromisoformat(action['proposed_start']), datetime.fromisoformat(action['proposed_end'])
                if _conflicts(connection, action['proposed_technician_id'], start, end, ignored_jobs, reserved):
                    raise ValueError("A replacement now has a conflicting booking. Recalculate before approval.")
                reserved.append((action['proposed_technician_id'], start, end))
        now = datetime.now(timezone.utc).isoformat()
        for action in actions:
            if not action['proposed_technician_id']:
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
            body = (f"Hello {details['name_alias']},\n\nYour {details['subtype']} appointment has been updated because "
                    f"the original technician reported sick. {details['technician']} is now scheduled from "
                    f"{action['proposed_start']} to {action['proposed_end']}.\n\nMendigo maintenance coordination")
            connection.execute("INSERT INTO customer_notifications VALUES (?,?,?,?,?,?,?,?,?)", (
                _id('NOTE'), details['request_id'], action['job_id'], 'SICK_LEAVE_RESCHEDULED',
                details['email'] or 'customer-contact-on-file', 'Maintenance appointment updated', body, 'DRAFT', now))
        connection.execute("UPDATE reschedule_plans SET plan_status='APPROVED', approved_by=?, approved_at=? WHERE plan_id=?",
                           (coordinator_id, now, plan_id))
        connection.execute("UPDATE operational_events SET event_status='RECOVERY_APPROVED' WHERE event_id=?", (plan['event_id'],))
        connection.commit()
        return get_plan(connection, plan_id)
    except Exception:
        connection.rollback()
        raise
