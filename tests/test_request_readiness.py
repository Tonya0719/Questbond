from src.validators import check_request_ready


def test_complete_request_is_ready(db):
    request = db.execute("SELECT * FROM structured_requests WHERE request_id='R001'").fetchone()
    assert check_request_ready(request) == (True, [])


def test_missing_service_information_needs_clarification(db):
    request = db.execute("SELECT * FROM structured_requests WHERE request_id='R009'").fetchone()
    ready, missing = check_request_ready(request)
    assert not ready
    assert "service_rule_id" in missing


def test_missing_window_needs_clarification(db):
    request = db.execute("SELECT * FROM structured_requests WHERE request_id='R010'").fetchone()
    ready, missing = check_request_ready(request)
    assert not ready
    assert {"window_start", "window_end"}.issubset(missing)
