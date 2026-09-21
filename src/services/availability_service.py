"""Customer-safe alternative appointment search after a requested window is full."""
from datetime import datetime, timedelta

from ..config import settings
from ..scheduling.eligibility import eligibility_reasons
from ..scheduling.ranking import rank_candidates
from ..scheduling.slots import find_earliest_feasible_slot
from ..scheduling.workload import get_assigned_workload, within_workload_capacity


def next_available_offer(connection, request_id: str, search_days: int = 14):
    request = connection.execute(
        "SELECT * FROM structured_requests WHERE request_id=?", (request_id,)
    ).fetchone()
    if not request or not request['service_rule_id'] or not request['window_end']:
        return None
    rule = connection.execute(
        "SELECT * FROM service_rules WHERE service_rule_id=?", (request['service_rule_id'],)
    ).fetchone()
    if not rule:
        return None
    company = connection.execute("SELECT * FROM company_profile LIMIT 1").fetchone()
    requested_end = datetime.fromisoformat(request['window_end'])
    duration = request['estimated_duration_min'] or rule['default_duration_min']

    candidates = []
    for offset in range(search_days + 1):
        day = requested_end.date() + timedelta(days=offset)
        day_start = datetime.combine(day, datetime.strptime(company['operating_start'], '%H:%M').time())
        day_end = datetime.combine(day, datetime.strptime(company['operating_end'], '%H:%M').time())
        window_start = max(requested_end, day_start) if offset == 0 else day_start
        if window_start >= day_end:
            continue
        for technician in connection.execute("SELECT * FROM technicians ORDER BY technician_id"):
            if eligibility_reasons(technician, rule):
                continue
            workload = get_assigned_workload(connection, technician['technician_id'], day.isoformat())
            if not within_workload_capacity(workload, duration, technician['max_workload_min']):
                continue
            slot = find_earliest_feasible_slot(
                connection, technician, window_start.isoformat(timespec='minutes'),
                day_end.isoformat(timespec='minutes'), duration, company, settings.slot_granularity_min)
            if slot:
                candidates.append({
                    'technician_id': technician['technician_id'],
                    'technician': technician['name_alias'],
                    'scheduled_start': slot[0].isoformat(timespec='minutes'),
                    'scheduled_end': slot[1].isoformat(timespec='minutes'),
                    'workload_before': workload,
                    'workload_after': workload + duration,
                    'projected_workload_ratio': (workload + duration) / technician['max_workload_min'],
                })
        if candidates:
            return rank_candidates(candidates)[0]
    return None
