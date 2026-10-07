"""Planning allowance between visits; not a map or live-traffic estimate."""
from datetime import datetime, timedelta

from ..validators import ACTIVE_ASSIGNMENT_STATUSES, ACTIVE_JOB_STATUSES

TRAVEL_BUFFER_MIN = 30


def needs_travel_gap(start, end, other_start, other_end):
    if start.date() != other_start.date():
        return False
    buffer = timedelta(minutes=TRAVEL_BUFFER_MIN)
    return start < other_end + buffer and end + buffer > other_start


def has_travel_conflict(connection, technician_id, start, end, ignored_jobs=(), reserved=()):
    rows = connection.execute('''SELECT s.job_id, s.scheduled_start, s.scheduled_end
        FROM schedules s JOIN jobs j USING(job_id)
        WHERE s.technician_id=? AND s.assignment_status IN (?,?) AND j.status IN (?,?)''',
        (technician_id, *sorted(ACTIVE_ASSIGNMENT_STATUSES), *sorted(ACTIVE_JOB_STATUSES))).fetchall()
    if any(row['job_id'] not in ignored_jobs and needs_travel_gap(
            start, end, datetime.fromisoformat(row['scheduled_start']), datetime.fromisoformat(row['scheduled_end']))
            for row in rows):
        return True
    return any(item[0] == technician_id and needs_travel_gap(start, end, item[1], item[2]) for item in reserved)
