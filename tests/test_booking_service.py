import pytest

from src.services.booking_service import confirm_recommendation, notification_draft
from src.services.request_service import submit_request


def request(db):
    return submit_request(db, "My kitchen pipe is leaking", contact={
        "name": "Demo resident", "email": "resident@example.com", "apartment": "Block A, unit 05-12"},
        scheduling_context="East 2030-01-15T10:00 2030-01-15T13:00")


def test_confirmation_creates_visible_booking_and_draft(db):
    response = request(db)
    assignment = response.result["assignment"]
    assert db.execute("SELECT COUNT(*) FROM schedules").fetchone()[0] == 16
    result = confirm_recommendation(db, assignment["assignment_id"], "coordinator")
    assert confirm_recommendation(db, assignment["assignment_id"], "coordinator")["job_id"] == result["job_id"]
    assert db.execute("SELECT COUNT(*) FROM schedules").fetchone()[0] == 17
    assert db.execute("SELECT raw_message FROM customer_requests WHERE request_id=?", (response.request_id,)).fetchone()[0] == "My kitchen pipe is leaking"
    draft = notification_draft(db, response.request_id)
    assert "resident@example.com" in draft and "Block A, unit 05-12" in draft
    assert result["job_id"] in draft


def test_stale_recommendation_is_rejected_without_partial_writes(db):
    first, second = request(db), request(db)
    assert first.result["assignment"]["technician_id"] == second.result["assignment"]["technician_id"]
    confirm_recommendation(db, first.result["assignment"]["assignment_id"], "coordinator")
    with pytest.raises(ValueError, match="SCHEDULE_CONFLICT"):
        confirm_recommendation(db, second.result["assignment"]["assignment_id"], "coordinator")
    assert db.execute("SELECT COUNT(*) FROM schedules").fetchone()[0] == 17
    assert db.execute("SELECT COUNT(*) FROM booking_confirmations").fetchone()[0] == 1


def test_invalid_email_does_not_create_request(db):
    with pytest.raises(ValueError, match="email"):
        submit_request(db, "tap leakage", contact={"name": "Demo", "email": "bad", "apartment": "Block A"})
    assert db.execute("SELECT COUNT(*) FROM customer_requests").fetchone()[0] == 10
