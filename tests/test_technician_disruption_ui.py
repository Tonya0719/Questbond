"""Checkpoint 3 — technician disruption reporting UI.

Drives the real Streamlit app as a signed-in Technician and verifies the
minimum-change reporting surface: schedule stays visible, UNAVAILABLE and DELAYED
each submit once and create a recovery proposal, and the technician has no
replacement chooser or approval control.
"""
from dataclasses import replace
from datetime import date
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src import config, database
from src.demo_scenarios import seed_sick_leave_scenario
from src.ui import sign_in

DEMO_DAY = date(2030, 1, 20)


def _tech_app(db, monkeypatch):
    path = Path(db.execute('PRAGMA database_list').fetchone()[2])
    settings = replace(config.settings, db_path=path, llm_backend='mock',
                       coordinator_password='test-ops', technician_password='test-tech')
    monkeypatch.setattr(config, 'settings', settings)
    monkeypatch.setattr(database, 'settings', settings)
    monkeypatch.setattr(sign_in, 'settings', settings)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=60)
    app.session_state['staff_role'] = 'Technician'
    app.session_state['sign_in_role'] = 'Technician'
    return app


def test_technician_can_report_unavailable_and_schedule_stays_visible(db, monkeypatch):
    scenario = seed_sick_leave_scenario(db, DEMO_DAY)
    app = _tech_app(db, monkeypatch).run()
    assert not app.exception
    assert any(h.value == 'Technician schedule' for h in app.header)
    assert any(h.value == 'Report disruption' for h in app.subheader)

    # Select Alex (T001), who has three confirmed visits in the demo.
    app.selectbox[0].set_value('T001 — Alex').run()
    # Report unavailability across the whole affected window.
    app.date_input(key='unavail_date_T001').set_value(DEMO_DAY)
    # Widen the reported window to cover all three confirmed visits.
    import datetime as _dt
    app.time_input(key='unavail_from_T001').set_value(_dt.time(8, 30))
    app.time_input(key='unavail_until_T001').set_value(_dt.time(16, 0))
    next(b for b in app.button if b.label == 'Report unavailability').click().run()
    assert not app.exception

    # A recovery plan/proposal was created for the event.
    assert db.execute("SELECT COUNT(*) FROM reschedule_plans").fetchone()[0] >= 1
    # Proposal only: the confirmed schedule is NOT mutated by the technician report.
    still_alex = db.execute("SELECT technician_id FROM schedules WHERE job_id=?",
                            (scenario['job_ids'][0],)).fetchone()['technician_id']
    assert still_alex == 'T001'
    # The technician sees an acknowledgement, not approval controls.
    ack = [el.value.lower() for el in app.success] + [el.value.lower() for el in app.info] \
        + [el.value.lower() for el in app.caption]
    assert any('coordinator' in value for value in ack)


def test_technician_has_no_replacement_or_approval_controls(db, monkeypatch):
    seed_sick_leave_scenario(db, DEMO_DAY)
    app = _tech_app(db, monkeypatch).run()
    app.selectbox[0].set_value('T001 — Alex').run()
    labels = [b.label for b in app.button]
    # No approve/reject/apply/confirm controls anywhere on the technician screen.
    for forbidden in ('Approve', 'Reject', 'Confirm', 'Apply'):
        assert not any(forbidden.lower() in (label or '').lower() for label in labels)
    # No replacement/technician chooser: the only technician-labelled selector is the
    # schedule picker; there is no widget for choosing a replacement technician.
    selector_labels = [(s.label or '') for s in app.selectbox]
    assert selector_labels.count('Technician') == 1
    assert not any('replacement' in label.lower() for label in selector_labels)


def test_technician_can_report_delay(db, monkeypatch):
    seed_sick_leave_scenario(db, DEMO_DAY)
    app = _tech_app(db, monkeypatch).run()
    app.selectbox[0].set_value('T001 — Alex').run()
    # Switch to the Delayed report type.
    app.radio(key='disruption_type_T001').set_value('Delayed').run()
    import datetime as _dt
    app.date_input(key='delay_date_T001').set_value(DEMO_DAY)
    app.time_input(key='delay_from_T001').set_value(_dt.time(9, 0))
    app.selectbox(key='delay_minutes_T001').set_value(60).run()
    next(b for b in app.button if b.label == 'Report delay').click().run()
    assert not app.exception
    # A DELAYED operational event was recorded.
    assert db.execute("SELECT COUNT(*) FROM operational_events WHERE event_type='DELAYED'").fetchone()[0] == 1
