from datetime import datetime
from src.scheduling.conflicts import has_schedule_conflict, intervals_overlap


def test_overlap_formula():
    at = datetime.fromisoformat
    assert intervals_overlap(at("2025-01-15T08:30"), at("2025-01-15T09:30"), at("2025-01-15T09:00"), at("2025-01-15T10:00"))
    assert not intervals_overlap(at("2025-01-15T08:00"), at("2025-01-15T09:00"), at("2025-01-15T09:00"), at("2025-01-15T10:00"))


def test_active_schedule_conflict(db):
    assert has_schedule_conflict(db, "T001", datetime.fromisoformat("2025-01-15T08:30"), datetime.fromisoformat("2025-01-15T09:30"))
