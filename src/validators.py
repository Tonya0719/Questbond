from __future__ import annotations

from datetime import datetime


ACTIVE_JOB_STATUSES = {"SCHEDULED", "IN_PROGRESS"}
ACTIVE_ASSIGNMENT_STATUSES = {"ASSIGNED", "CONFIRMED"}


def parse_csv_set(value: str | None) -> set[str]:
    return {item.strip() for item in (value or "").split("|") if item.strip()}


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def check_request_ready(request) -> tuple[bool, list[str]]:
    fields = ("service_rule_id", "zone", "window_start", "window_end", "estimated_duration_min")
    missing = [field for field in fields if not request[field] if field != "estimated_duration_min"]
    if request["estimated_duration_min"] is None:
        missing.append("estimated_duration_min")
    return not missing, missing
