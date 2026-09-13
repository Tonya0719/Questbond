from datetime import datetime, time, timedelta

from .conflicts import has_schedule_conflict


def _time(value: str) -> time:
    return time.fromisoformat(value)


def ceil_to_granularity(value: datetime, minutes: int) -> datetime:
    midnight = value.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed = int((value - midnight).total_seconds() // 60)
    rounded = ((elapsed + minutes - 1) // minutes) * minutes
    return midnight + timedelta(minutes=rounded)


def find_earliest_feasible_slot(connection, technician, window_start: str, window_end: str,
                                duration_min: int, company, granularity_min: int = 30):
    customer_start, customer_end = datetime.fromisoformat(window_start), datetime.fromisoformat(window_end)
    day = customer_start.date()
    if customer_end.date() != day:
        return None
    shift_start = datetime.combine(day, _time(technician["shift_start"]))
    shift_end = datetime.combine(day, _time(technician["shift_end"]))
    operating_start = datetime.combine(day, _time(company["operating_start"]))
    operating_end = datetime.combine(day, _time(company["operating_end"]))
    cursor = ceil_to_granularity(max(customer_start, shift_start, operating_start), granularity_min)
    latest_end = min(customer_end, shift_end, operating_end)
    while cursor + timedelta(minutes=duration_min) <= latest_end:
        end = cursor + timedelta(minutes=duration_min)
        if not has_schedule_conflict(connection, technician["technician_id"], cursor, end):
            return cursor, end
        cursor += timedelta(minutes=granularity_min)
    return None
