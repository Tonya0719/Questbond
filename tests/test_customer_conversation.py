from dataclasses import replace
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from src import config, database
from src.services.request_service import submit_request, continue_request
from src.services.booking_service import confirm_recommendation
from src.ui import sign_in


def unavailable_request(db):
    db.execute("UPDATE technicians SET status='UNAVAILABLE' WHERE technician_id!='T001'")
    db.execute("UPDATE technicians SET status='AVAILABLE', shift_start='14:00' WHERE technician_id='T001'")
    db.commit()
    return submit_request(db, 'Aircon not cooling', customer_id_or_new='C001', scheduling_context='East 2030-01-15T10:00 2030-01-15T13:00')


def test_no_slot_then_customer_requests_another_window(db):
    first = unavailable_request(db)
    assert first.workflow_status.value == 'NO_FEASIBLE_ASSIGNMENT'
    assert first.result['assignment']['technician_id'] is None
    second = continue_request(db, first.session_id, 'Please check 2030-01-15T14:00 to 2030-01-15T17:00')
    assert second.request_id == first.request_id
    assert second.session_id != first.session_id
    assert second.workflow_status.value == 'RECOMMENDATION_CREATED'
    assert second.result['assignment']['technician_id'] == 'T001'
    assert second.result['assignment']['scheduled_start'] == '2030-01-15T14:00'
    assert db.execute('SELECT COUNT(*) FROM schedules').fetchone()[0] == 16
    public = '\n'.join(row[0] for row in db.execute('SELECT content FROM customer_messages'))
    assert 'No technician is free' in public
    assert 'Confirmation is the next step' in public
    assert not any(term in public for term in ('Blair', 'workload', 'tiebreak', 'certification', 'Customer-provided booking details', 'T14:00'))
    assert db.execute('SELECT COUNT(*) FROM assignment_results WHERE request_id=?', (first.request_id,)).fetchone()[0] == 2
    confirm_recommendation(db, second.result['assignment']['assignment_id'], 'demo-coordinator')
    with pytest.raises(ValueError, match='confirmed visit'):
        continue_request(db, first.session_id, '2030-01-15T15:00 2030-01-15T17:00')


def test_customer_screen_hides_internal_details_and_offers_new_window(db, monkeypatch):
    response = unavailable_request(db)
    settings = replace(config.settings, db_path=Path(db.execute('PRAGMA database_list').fetchone()[2]), llm_backend='mock')
    monkeypatch.setattr(config, 'settings', settings)
    monkeypatch.setattr(database, 'settings', settings)
    monkeypatch.setattr(sign_in, 'settings', settings)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=30)
    app.session_state['agent_session_id'] = response.session_id
    app.run()
    assert not app.exception
    assert any(button.label == 'Accept this time' for button in app.button)
    assert any(button.label == 'Choose another time' for button in app.button)
    visible = '\n'.join(element.value for element in app.text)
    assert 'No technician is free' in visible
    assert 'workload' not in visible and 'Blair' not in visible
    assert not app.json
    next(button for button in app.button if button.label == 'Accept this time').click().run()
    assert not app.exception
    assert db.execute('SELECT COUNT(*) FROM booking_confirmations WHERE request_id=?',
                      (response.request_id,)).fetchone()[0] == 1
    assert any('Your visit is confirmed' in element.value for element in app.success)
    assert any('Your appointment with' in element.value and 'is confirmed' in element.value
               for element in app.text)
    # Legacy conversations must also be projected safely, not shown as debug logs.
    db.execute('DELETE FROM customer_messages')
    db.commit()
    app.run()
    assert not app.exception
    assert not any('workload' in element.value for element in app.text)
