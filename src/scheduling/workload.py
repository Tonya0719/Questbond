from ..validators import ACTIVE_ASSIGNMENT_STATUSES, ACTIVE_JOB_STATUSES


def get_assigned_workload(connection, technician_id: str, work_date: str) -> int:
    row = connection.execute(
        """SELECT COALESCE(SUM(j.estimated_duration_min),0) FROM schedules s
           JOIN jobs j ON j.job_id=s.job_id
           WHERE s.technician_id=? AND date(s.scheduled_start)=?
             AND s.assignment_status IN (?,?) AND j.status IN (?,?)""",
        (technician_id, work_date, *sorted(ACTIVE_ASSIGNMENT_STATUSES), *sorted(ACTIVE_JOB_STATUSES)),
    ).fetchone()
    return int(row[0])


def within_workload_capacity(current: int, duration: int, maximum: int) -> bool:
    return current + duration <= maximum
