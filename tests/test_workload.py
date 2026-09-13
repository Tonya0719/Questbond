from src.scheduling.workload import get_assigned_workload, within_workload_capacity


def test_workload_is_calculated_from_active_assignments(db):
    assert get_assigned_workload(db, "T006", "2025-01-15") == 180


def test_capacity_boundary():
    assert within_workload_capacity(300, 120, 420)
    assert not within_workload_capacity(330, 120, 420)
