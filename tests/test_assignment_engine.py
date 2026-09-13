import json
from src.scheduling.assignment_engine import assign_technician


def test_assignment_is_deterministic_and_persisted(db):
    result = assign_technician("R001", db)
    assert result.decision_status == "ASSIGNED"
    assert result.technician_id == "T002"
    assert db.execute("SELECT COUNT(*) FROM assignment_results WHERE request_id='R001'").fetchone()[0] == 1
    assert result.recommendation_reason["ranking_reason"]


def test_incomplete_request_does_not_run_assignment(db):
    result = assign_technician("R010", db)
    assert result.decision_status == "NEEDS_CLARIFICATION"
    assert result.technician_id is None


def test_no_feasible_technician(db):
    db.execute("UPDATE structured_requests SET window_start='2025-01-15T17:30', window_end='2025-01-15T18:00', estimated_duration_min=90, ready_for_scheduling=1 WHERE request_id='R001'")
    db.commit()
    result = assign_technician("R001", db)
    assert result.decision_status == "NO_FEASIBLE_TECHNICIAN"
    assert "excluded_technicians" in result.recommendation_reason


def test_recommendation_does_not_modify_schedule(db):
    before = db.execute("SELECT COUNT(*) FROM schedules").fetchone()[0]
    assign_technician("R002", db)
    assert db.execute("SELECT COUNT(*) FROM schedules").fetchone()[0] == before
