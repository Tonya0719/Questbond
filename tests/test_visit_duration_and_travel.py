from datetime import datetime

import pytest

from src.services.booking_service import confirm_recommendation
from src.services.request_service import submit_request, continue_request
from src.services.availability_service import next_available_offer
from src.services.visit_details import visit_details
from src.services.disruption_service import create_delay_plan, approve_plan
from src.scheduling.travel import has_travel_conflict


def request(db, start='10:00', end='14:00', **kwargs):
    return submit_request(db, 'Aircon not cooling', customer_id_or_new='C001',
        scheduling_context=f'East 2030-01-15T{start} 2030-01-15T{end}', **kwargs)


def only_one_technician(db):
    db.execute("UPDATE technicians SET status='UNAVAILABLE' WHERE technician_id!='T001'")
    db.commit()


def test_one_hour_with_travel_gap_inside_wider_window(db):
    only_one_technician(db)
    first = request(db, reserved_duration_min=60)
    assignment = first.result['assignment']
    assert assignment['scheduled_start'] == '2030-01-15T10:00'
    assert assignment['scheduled_end'] == '2030-01-15T11:00'
    confirm_recommendation(db, assignment['assignment_id'], 'coordinator')
    second = request(db, reserved_duration_min=60)
    assert second.result['assignment']['scheduled_start'] == '2030-01-15T11:30'
    assert second.result['assignment']['scheduled_end'] == '2030-01-15T12:30'
    confirm_recommendation(db, second.result['assignment']['assignment_id'], 'coordinator')
    details = visit_details(db, first.request_id)
    assert details['default_duration_min'] == 90
    assert details['estimated_duration_min'] == 60
    assert details['window_end'] == '2030-01-15T14:00'
    assert details['confirmed']


def test_default_remains_service_estimate(db):
    response = request(db)
    assignment = response.result['assignment']
    duration = datetime.fromisoformat(assignment['scheduled_end']) - datetime.fromisoformat(assignment['scheduled_start'])
    assert duration.total_seconds() == 90 * 60
    confirm_recommendation(db, assignment['assignment_id'], 'coordinator')


def test_gap_required_before_following_booking(db):
    only_one_technician(db)
    later = request(db, '11:00', '12:00', reserved_duration_min=60)
    confirm_recommendation(db, later.result['assignment']['assignment_id'], 'coordinator')
    earlier = request(db, '10:00', '11:00', reserved_duration_min=60)
    assert earlier.workflow_status.value == 'NO_FEASIBLE_ASSIGNMENT'
    offer = next_available_offer(db, earlier.request_id)
    assert offer['scheduled_start'] == '2030-01-15T12:30'
    assert offer['scheduled_end'] == '2030-01-15T13:30'


def test_travel_only_conflict_rechecked_at_confirmation(db):
    only_one_technician(db)
    early = request(db, '10:00', '11:00', reserved_duration_min=60)
    late = request(db, '11:00', '12:00', reserved_duration_min=60)
    confirm_recommendation(db, early.result['assignment']['assignment_id'], 'coordinator')
    with pytest.raises(ValueError, match='INSUFFICIENT_TRAVEL_TIME'):
        confirm_recommendation(db, late.result['assignment']['assignment_id'], 'coordinator')
    assert db.execute('SELECT COUNT(*) FROM booking_confirmations').fetchone()[0] == 1


def test_duration_choice_survives_new_window(db):
    response = request(db, '10:00', '10:30', reserved_duration_min=60)
    assert response.workflow_status.value == 'NO_FEASIBLE_ASSIGNMENT'
    response = continue_request(db, response.session_id, 'Please check 2030-01-15T14:00 to 2030-01-15T16:00')
    assert visit_details(db, response.request_id)['estimated_duration_min'] == 60
    confirm_recommendation(db, response.result['assignment']['assignment_id'], 'coordinator')


def test_idempotency_rejects_changed_duration(db):
    request(db, idempotency_key='same')
    with pytest.raises(ValueError, match='different details'):
        request(db, idempotency_key='same', reserved_duration_min=60)


@pytest.mark.parametrize('duration', [0, -1, 30, 90, True, 60.0, '60'])
def test_invalid_duration_rejected_before_writes(db, duration):
    count = db.execute('SELECT COUNT(*) FROM customer_requests').fetchone()[0]
    with pytest.raises(ValueError, match='one-hour'):
        request(db, reserved_duration_min=duration)
    assert db.execute('SELECT COUNT(*) FROM customer_requests').fetchone()[0] == count


def test_buffer_boundary_cancelled_job_and_other_days(db):
    first = request(db, reserved_duration_min=60)
    job = confirm_recommendation(db, first.result['assignment']['assignment_id'], 'coordinator')
    tech = first.result['assignment']['technician_id']
    dt = datetime.fromisoformat
    assert has_travel_conflict(db, tech, dt('2030-01-15T11:29'), dt('2030-01-15T12:29'))
    assert not has_travel_conflict(db, tech, dt('2030-01-15T11:30'), dt('2030-01-15T12:30'))
    assert not has_travel_conflict(db, tech, dt('2030-01-16T10:00'), dt('2030-01-16T11:00'))
    db.execute("UPDATE jobs SET status='CANCELLED' WHERE job_id=?", (job['job_id'],))
    assert not has_travel_conflict(db, tech, dt('2030-01-15T11:00'), dt('2030-01-15T12:00'))


def test_recovery_preserves_travel_gaps_and_display_uses_new_time(db):
    only_one_technician(db)
    first = request(db, reserved_duration_min=60)
    confirm_recommendation(db, first.result['assignment']['assignment_id'], 'coordinator')
    second = request(db, reserved_duration_min=60)
    confirm_recommendation(db, second.result['assignment']['assignment_id'], 'coordinator')
    plan = create_delay_plan(db, 'T001', '2030-01-15T10:00', 30)
    # 10:30-11:30 would consume the travel gap before the 11:30 visit.
    assert plan['actions'][0]['proposed_start'] == '2030-01-15T13:00'
    approve_plan(db, plan['plan']['plan_id'], 'coordinator')
    assert visit_details(db, first.request_id)['scheduled_start'] == '2030-01-15T13:00'


def test_customer_form_and_tracker_show_one_hour_separately(db, monkeypatch):
    from dataclasses import replace
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from src import config, database
    from src.ui import sign_in

    settings = replace(config.settings, db_path=Path(db.execute('PRAGMA database_list').fetchone()[2]), llm_backend='mock')
    for module in (config, database, sign_in):
        monkeypatch.setattr(module, 'settings', settings)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=30).run()
    for field in app.text_input:
        field.set_value({'Name': 'Demo', 'Email': 'demo@example.com', 'Apartment / unit': 'Block A unit 01'}[field.label])
    app.text_area[0].set_value('Aircon not cooling')
    next(button for button in app.button if button.label.startswith('Plan my visit')).click().run()
    assert not app.exception
    visible = '\n'.join(element.value for element in app.text)
    assert 'Your availability:' in visible
    assert 'Estimated work time: about 90 minutes' in visible
    assert 'Visit length: 60 minutes' in visible
    assert not any(field.label == 'Visit length' for field in app.selectbox)
    assert 'Proposed appointment:' in visible
    assert any('follow-up' in element.value for element in app.warning)
    assert any('30 minutes of travel' in element.value for element in app.caption)
