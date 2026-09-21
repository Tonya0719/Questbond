from datetime import datetime

from ..validators import ACTIVE_ASSIGNMENT_STATUSES, ACTIVE_JOB_STATUSES


def intervals_overlap(new_start: datetime, new_end: datetime, existing_start: datetime, existing_end: datetime) -> bool:
    return new_start < existing_end and new_end > existing_start


def has_schedule_conflict(connection, technician_id: str, start: datetime, end: datetime) -> bool:
    unavailable = connection.execute(
        """SELECT unavailable_from, unavailable_until FROM operational_events
           WHERE technician_id=? AND event_status IN ('OPEN','RECOVERY_APPROVED')""",
        (technician_id,),
    ).fetchall()
    if any(intervals_overlap(start, end, datetime.fromisoformat(row[0]), datetime.fromisoformat(row[1]))
           for row in unavailable):
        return True
    rows = connection.execute(
        """SELECT s.scheduled_start, s.scheduled_end FROM schedules s
           JOIN jobs j ON j.job_id=s.job_id
           WHERE s.technician_id=? AND s.assignment_status IN (?,?) AND j.status IN (?,?)""",
        (technician_id, *sorted(ACTIVE_ASSIGNMENT_STATUSES), *sorted(ACTIVE_JOB_STATUSES)),
    ).fetchall()
    return any(
        intervals_overlap(start, end, datetime.fromisoformat(row[0]), datetime.fromisoformat(row[1])) for row in rows
    )
