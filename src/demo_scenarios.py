"""Repeatable, synthetic scenarios used only for demonstrations and evaluation."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .scheduling.conflicts import has_schedule_conflict
from .scheduling.eligibility import eligibility_reasons


def seed_sick_leave_scenario(connection, work_date=None) -> dict:
    """Create three future Alex bookings with qualified replacement options."""
    day = work_date or (datetime.now(ZoneInfo('Asia/Singapore')).date() + timedelta(days=2))
    tag = day.strftime('%Y%m%d')
    now = datetime.now(timezone.utc).isoformat()
    connection.execute("""INSERT OR IGNORE INTO technicians VALUES
        ('T009','Jordan','aircon_service|aircon_diagnostics|aircon_repair','REFRIGERANT','08:00','18:00','AVAILABLE','East',480)""")

    cases = [
        ('01', 'AC-ROUTINE', 'Routine servicing', 'East', '09:00', '10:00', '08:30', '11:00', 'NORMAL', 60,
         'The living room aircon needs routine servicing.'),
        ('02', 'AC-LEAK', 'Water leakage / repair', 'East', '11:00', '12:30', '10:30', '14:00', 'HIGH', 90,
         'The bedroom aircon is leaking water.'),
        ('03', 'AC-DIAG', 'Not cooling / diagnosis', 'Central', '14:00', '15:30', '13:00', '17:00', 'NORMAL', 90,
         'The aircon runs but is not cooling.'),
    ]
    request_ids, job_ids = [], []
    for suffix, rule, subtype, zone, start, end, window_start, window_end, priority, duration, message in cases:
        customer_id = f'DEMO-CUST-{tag}-{suffix}'
        request_id = f'DEMO-REQ-{tag}-{suffix}'
        assignment_id = f'DEMO-ASG-{tag}-{suffix}'
        session_id = f'DEMO-SES-{tag}-{suffix}'
        job_id = f'DEMO-JOB-{tag}-{suffix}'
        start_at, end_at = f'{day.isoformat()}T{start}', f'{day.isoformat()}T{end}'
        window_from, window_until = f'{day.isoformat()}T{window_start}', f'{day.isoformat()}T{window_end}'
        connection.execute("INSERT OR IGNORE INTO customers VALUES (?,?,?,?,?,?,?)", (
            customer_id, f'Demo Resident {suffix}', 'RESIDENTIAL', 'EMAIL', f'{suffix}01', zone, f'{window_start}-{window_end}'))
        connection.execute("INSERT OR IGNORE INTO customer_requests VALUES (?,?,?,?,?,?)",
            (request_id, customer_id, now, 'WEB', message, 'en'))
        connection.execute("INSERT OR IGNORE INTO request_contacts VALUES (?,?,?,?)",
            (request_id, f'Demo Resident {suffix}', f'resident{suffix}@example.com', f'Block Demo, unit #{suffix}-01'))
        connection.execute("INSERT OR IGNORE INTO structured_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
            request_id, customer_id, rule, 'Air-conditioning', subtype, zone, priority,
            window_from, window_until, duration, '[]', 1))
        connection.execute("INSERT OR IGNORE INTO agent_sessions VALUES (?,?,?,?,?,?,?)",
            (session_id, request_id, customer_id, 'scheduling_operations_agent', 'RECOMMENDATION_CREATED', now, now))
        connection.execute("INSERT OR IGNORE INTO assignment_results VALUES (?,?,?,?,?,?,?,?,?,?)", (
            assignment_id, request_id, 'T001', start_at, end_at, 'ASSIGNED', 0, duration,
            json.dumps({'demo': True, 'ranking_reason': 'prepared sick-leave scenario'}), now))
        connection.execute("INSERT OR IGNORE INTO jobs VALUES (?,?,?,?,?,?,?,?,?)",
            (job_id, customer_id, rule, priority, duration, window_from, window_until, zone, 'SCHEDULED'))
        connection.execute("INSERT OR IGNORE INTO schedules VALUES (?,?,?,?,?,?)",
            (job_id, 'T001', start_at, end_at, 'CONFIRMED', 1))
        connection.execute("INSERT OR IGNORE INTO booking_confirmations VALUES (?,?,?,?,?)",
            (assignment_id, request_id, job_id, 'demo-coordinator', now))
        request_ids.append(request_id)
        job_ids.append(job_id)

    # These synthetic commitments make the recovery decision non-trivial:
    # Blair can preserve the first appointment; Jordan is occupied until 10:30.
    blocker_customer = f'DEMO-CUST-{tag}-BLOCK'
    connection.execute("INSERT OR IGNORE INTO customers VALUES (?,?,?,?,?,?,?)",
        (blocker_customer, 'Existing Resident', 'RESIDENTIAL', 'EMAIL', '0999', 'East', 'morning'))
    blocker_job = f'DEMO-BLOCK-{tag}-01'
    connection.execute("INSERT OR IGNORE INTO jobs VALUES (?,?,?,?,?,?,?,?,?)", (
        blocker_job, blocker_customer, 'AC-ROUTINE', 'NORMAL', 90,
        f'{day.isoformat()}T09:00', f'{day.isoformat()}T11:00', 'East', 'SCHEDULED'))
    connection.execute("INSERT OR IGNORE INTO schedules VALUES (?,?,?,?,?,?)",
        (blocker_job, 'T009', f'{day.isoformat()}T09:00', f'{day.isoformat()}T10:30', 'CONFIRMED', 1))
    connection.commit()
    return {
        'scenario': 'Technician sick leave', 'technician_id': 'T001', 'technician': 'Alex',
        'unavailable_from': f'{day.isoformat()}T08:30', 'unavailable_until': f'{day.isoformat()}T16:00',
        'request_ids': request_ids, 'job_ids': job_ids,
    }


FUTURE_SERVICE_RULES = [
    ('PA-WALL', 'Painting', 'Interior wall painting', 'painting|surface_prep', '', 240, 'NORMAL', 'zone|appointment_window'),
    ('PA-TOUCH', 'Painting', 'Wall touch-up', 'painting', '', 120, 'NORMAL', 'zone|appointment_window'),
    ('CA-DOOR', 'Carpentry', 'Door / frame repair', 'carpentry|door_repair', '', 120, 'NORMAL', 'zone|appointment_window'),
    ('CA-CABINET', 'Carpentry', 'Cabinet repair', 'carpentry|cabinet_repair', '', 150, 'NORMAL', 'zone|appointment_window'),
    ('MA-CRACK', 'Masonry / cement', 'Wall crack / cement patch', 'masonry|cement_repair', '', 180, 'NORMAL', 'zone|appointment_window'),
    ('MA-TILE', 'Masonry / cement', 'Tile / cement repair', 'masonry|tile_repair', '', 180, 'NORMAL', 'zone|appointment_window'),
]

FUTURE_TECHNICIANS = [
    ('T009', 'Jordan', 'aircon_service|aircon_diagnostics|aircon_repair', 'REFRIGERANT', '08:00', '18:00', 'AVAILABLE', 'East', 480),
    ('T010', 'Imani', 'painting|surface_prep', '', '08:00', '17:00', 'AVAILABLE', 'Central', 420),
    ('T011', 'Jules', 'painting|surface_prep', '', '09:00', '18:00', 'AVAILABLE', 'West', 420),
    ('T012', 'Kiran', 'carpentry|door_repair|cabinet_repair', '', '08:00', '17:00', 'AVAILABLE', 'North', 420),
    ('T013', 'Lee', 'carpentry|door_repair|cabinet_repair', '', '09:00', '18:00', 'AVAILABLE', 'South', 420),
    ('T014', 'Morgan', 'masonry|cement_repair|tile_repair', '', '08:00', '17:00', 'AVAILABLE', 'Central', 420),
    ('T015', 'Noor', 'masonry|cement_repair|tile_repair', '', '09:00', '18:00', 'AVAILABLE', 'East', 420),
    ('T016', 'Parker', 'plumbing_repair|masonry|cement_repair', '', '08:00', '17:00', 'AVAILABLE', 'West', 420),
    ('T017', 'Quinn', 'electrical_repair|electrical_diagnostics|carpentry|door_repair', 'ELECTRICAL', '08:00', '17:00', 'AVAILABLE', 'North', 420),
    ('T018', 'Riley', 'aircon_service|aircon_diagnostics|aircon_repair', 'REFRIGERANT', '09:00', '18:00', 'AVAILABLE', 'South', 420),
]


def seed_future_workforce(connection, start_date=date(2026, 9, 21), end_date=date(2026, 10, 10)) -> dict:
    """Add a deterministic 20-day workforce with two saturated test windows per day."""
    if end_date < start_date:
        raise ValueError('Dataset end date must not be before its start date.')
    for row in FUTURE_SERVICE_RULES:
        connection.execute("INSERT OR IGNORE INTO service_rules VALUES (?,?,?,?,?,?,?,?)", row)
    for row in FUTURE_TECHNICIANS:
        connection.execute("INSERT OR IGNORE INTO technicians VALUES (?,?,?,?,?,?,?,?,?)", row)
    for number in range(1, 61):
        zone = ('East', 'West', 'North', 'South', 'Central')[(number - 1) % 5]
        connection.execute("INSERT OR IGNORE INTO customers VALUES (?,?,?,?,?,?,?)", (
            f'FUT-C{number:03d}', f'Synthetic Resident {number:03d}', 'RESIDENTIAL', 'EMAIL',
            f'{1000 + number}', zone, '09:00-17:00'))

    templates = [
        ('AC-LEAK', ('T001', 'T002', 'T009', 'T018'), '09:00', '10:30', 90, 'East', 'HIGH'),
        ('PL-LEAK', ('T004', 'T005', 'T016'), '10:00', '11:00', 60, 'North', 'NORMAL'),
        ('EL-REPAIR', ('T006', 'T007', 'T017'), '11:00', '12:00', 60, 'Central', 'NORMAL'),
        ('PA-WALL', ('T010', 'T011'), '09:00', '13:00', 240, 'West', 'NORMAL'),
        ('CA-DOOR', ('T012', 'T013', 'T017'), '13:00', '15:00', 120, 'South', 'NORMAL'),
        ('MA-CRACK', ('T014', 'T015', 'T016'), '14:00', '17:00', 180, 'Central', 'NORMAL'),
    ]
    day, day_index, customer_index = start_date, 0, 1
    while day <= end_date:
        for slot_index, (rule, technicians, start, end, duration, zone, priority) in enumerate(templates, 1):
            technician = technicians[day_index % len(technicians)]
            job_id = f'FUT-JOB-{day.strftime("%Y%m%d")}-{slot_index:02d}'
            customer_id = f'FUT-C{customer_index:03d}'
            customer_index = customer_index % 60 + 1
            connection.execute("INSERT OR IGNORE INTO jobs VALUES (?,?,?,?,?,?,?,?,?)", (
                job_id, customer_id, rule, priority, duration, f'{day.isoformat()}T{start}',
                f'{day.isoformat()}T{end}', zone, 'SCHEDULED'))
            connection.execute("INSERT OR IGNORE INTO schedules VALUES (?,?,?,?,?,?)", (
                job_id, technician, f'{day.isoformat()}T{start}', f'{day.isoformat()}T{end}', 'CONFIRMED', 1))
        day += timedelta(days=1)
        day_index += 1

    # Remove the earlier all-day synthetic block if this database was generated by
    # a prior prototype, then create two evidence-backed saturation cases per day.
    connection.execute("DELETE FROM operational_events WHERE event_id LIKE 'FUT-CAP-%'")
    case_rules = ('AC-ROUTINE', 'PL-LEAK', 'EL-REPAIR', 'PA-TOUCH', 'CA-DOOR', 'MA-CRACK')
    day, day_index = start_date, 0
    while day <= end_date:
        for sequence, (rule_id, start_hour) in enumerate(((case_rules[day_index % 6], 9),
                                                          (case_rules[(day_index + 3) % 6], 14)), 1):
            rule = connection.execute("SELECT * FROM service_rules WHERE service_rule_id=?", (rule_id,)).fetchone()
            start = datetime.combine(day, datetime.min.time()).replace(hour=start_hour)
            end = start + timedelta(minutes=rule['default_duration_min'])
            case_id = f'CAP-{day.strftime("%Y%m%d")}-{sequence}'
            connection.execute("INSERT OR IGNORE INTO demo_capacity_cases VALUES (?,?,?,?,?,?,?)", (
                case_id, day.isoformat(), rule_id, start.isoformat(timespec='minutes'),
                end.isoformat(timespec='minutes'), 'NO_FEASIBLE_TECHNICIAN',
                f"All qualified technicians have confirmed work during this {rule['subtype']} window."))
            candidates = [tech for tech in connection.execute("SELECT * FROM technicians ORDER BY technician_id")
                          if not eligibility_reasons(tech, rule)]
            for tech in candidates:
                if has_schedule_conflict(connection, tech['technician_id'], start, end):
                    continue
                job_id = f'FUT-CAPJOB-{case_id}-{tech["technician_id"]}'
                customer_id = f'FUT-C{customer_index:03d}'
                customer_index = customer_index % 60 + 1
                connection.execute("INSERT OR IGNORE INTO jobs VALUES (?,?,?,?,?,?,?,?,?)", (
                    job_id, customer_id, rule_id, 'NORMAL', rule['default_duration_min'],
                    start.isoformat(timespec='minutes'), end.isoformat(timespec='minutes'),
                    connection.execute("SELECT current_zone FROM technicians WHERE technician_id=?",
                                       (tech['technician_id'],)).fetchone()[0], 'SCHEDULED'))
                connection.execute("INSERT OR IGNORE INTO schedules VALUES (?,?,?,?,?,?)", (
                    job_id, tech['technician_id'], start.isoformat(timespec='minutes'),
                    end.isoformat(timespec='minutes'), 'CONFIRMED', 1))
        day += timedelta(days=1)
        day_index += 1
    connection.commit()
    jobs = connection.execute("SELECT COUNT(*) FROM jobs WHERE job_id LIKE 'FUT-%'").fetchone()[0]
    technicians = connection.execute("SELECT COUNT(*) FROM technicians").fetchone()[0]
    cases = connection.execute("SELECT COUNT(*) FROM demo_capacity_cases WHERE work_date BETWEEN ? AND ?",
                               (start_date.isoformat(), end_date.isoformat())).fetchone()[0]
    return {'start_date': start_date.isoformat(), 'end_date': end_date.isoformat(),
            'scheduled_jobs': jobs, 'capacity_cases': cases,
            'technicians': technicians, 'customers': 60, 'domains': 6}
