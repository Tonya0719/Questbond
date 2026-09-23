"""Checkpoint 4 — Coordinator Recovery Plans UI (upgraded prototype).

Drives the app as a signed-in Coordinator and verifies the generalised recovery
section: governance flags visible, approval driven by backend policy, reject
preserves the schedule, unresolved cannot be applied, and notices stay drafts.
"""
from dataclasses import replace
from datetime import date
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src import config, database
from src.demo_scenarios import seed_sick_leave_scenario
from src.services.disruption_service import create_sick_leave_plan
from src.ui import sign_in

DEMO_DAY = date(2030, 1, 20)


def _coordinator_app(db, monkeypatch):
    path = Path(db.execute('PRAGMA database_list').fetchone()[2])
    settings = replace(config.settings, db_path=path, llm_backend='mock',
                       coordinator_password='test-ops', technician_password='test-tech')
    monkeypatch.setattr(config, 'settings', settings)
    monkeypatch.setattr(database, 'settings', settings)
    monkeypatch.setattr(sign_in, 'settings', settings)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=90)
    app.session_state['staff_role'] = 'Coordinator'
    app.session_state['sign_in_role'] = 'Coordinator'
    return app


def _visible_text(app):
    parts = []
    for group in (app.markdown, app.caption, app.info, app.warning, app.success, app.error):
        parts.extend(el.value for el in group)
    return '\n'.join(parts)


def test_recovery_plans_section_shows_governance_and_before_after(db, monkeypatch):
    scenario = seed_sick_leave_scenario(db, DEMO_DAY)
    plan = create_sick_leave_plan(db, scenario['technician_id'],
                                  scenario['unavailable_from'], scenario['unavailable_until'])
    app = _coordinator_app(db, monkeypatch)
    app.session_state['recovery_plan_id'] = plan['plan']['plan_id']
    app.run()
    assert not app.exception
    # Governance / approval metric visible for confirmed reassignments.
    assert any('Approval required' in (c.label or '') for c in app.metric)
    # The approval-policy warning for confirmed changes is shown.
    assert 'require your approval' in _visible_text(app).lower()
    # Approve / Reject / Recalculate controls exist.
    labels = [b.label for b in app.button]
    assert 'Approve' in labels
    assert 'Reject' in labels
    assert 'Recalculate' in labels


def test_reject_preserves_schedule_and_writes_no_notice(db, monkeypatch):
    scenario = seed_sick_leave_scenario(db, DEMO_DAY)
    plan = create_sick_leave_plan(db, scenario['technician_id'],
                                  scenario['unavailable_from'], scenario['unavailable_until'])
    app = _coordinator_app(db, monkeypatch)
    app.session_state['recovery_plan_id'] = plan['plan']['plan_id']
    app.run()
    next(b for b in app.button if b.label == 'Reject').click().run()
    next(b for b in app.button if b.label == 'Confirm rejection').click().run()
    assert not app.exception
    # Schedule unchanged; no customer notices.
    techs = [row['technician_id'] for row in db.execute(
        f"SELECT technician_id FROM schedules WHERE job_id IN ({','.join('?' for _ in scenario['job_ids'])}) ORDER BY job_id",
        scenario['job_ids'])]
    assert techs == ['T001', 'T001', 'T001']
    assert db.execute('SELECT COUNT(*) FROM customer_notifications').fetchone()[0] == 0
    assert db.execute("SELECT plan_status FROM reschedule_plans WHERE plan_id=?",
                      (plan['plan']['plan_id'],)).fetchone()['plan_status'] == 'REJECTED'


def test_approve_applies_and_drafts_notices(db, monkeypatch):
    scenario = seed_sick_leave_scenario(db, DEMO_DAY)
    plan = create_sick_leave_plan(db, scenario['technician_id'],
                                  scenario['unavailable_from'], scenario['unavailable_until'])
    app = _coordinator_app(db, monkeypatch)
    app.session_state['recovery_plan_id'] = plan['plan']['plan_id']
    app.run()
    next(b for b in app.button if b.label == 'Approve').click().run()
    assert not app.exception
    assert db.execute("SELECT plan_status FROM reschedule_plans WHERE plan_id=?",
                      (plan['plan']['plan_id'],)).fetchone()['plan_status'] == 'APPROVED'
    notices = db.execute('SELECT delivery_status FROM customer_notifications').fetchall()
    assert len(notices) == 3
    assert all(row['delivery_status'] == 'DRAFT' for row in notices)


def test_unresolved_plan_disables_approve(db, monkeypatch):
    # Make AC-DIAG unresolvable: only T001 can do it; disable everyone else's status.
    db.execute("UPDATE technicians SET status='UNAVAILABLE' WHERE technician_id!='T001'")
    db.commit()
    # Seed a single confirmed AC-DIAG job for T001, then report unavailable.
    db.execute("INSERT OR IGNORE INTO customers VALUES ('CU','R','RESIDENTIAL','EMAIL','1','East','any')")
    db.execute("INSERT INTO customer_requests VALUES ('RQ','CU','x','WEB','m','en')")
    db.execute("INSERT INTO structured_requests VALUES ('RQ','CU','AC-DIAG','Air-conditioning','Diag','East','NORMAL',?,?,90,'[]',1)",
               (f"{DEMO_DAY.isoformat()}T09:00", f"{DEMO_DAY.isoformat()}T11:00"))
    db.execute("INSERT INTO request_contacts VALUES ('RQ','R','r@example.com','U1')")
    db.execute("INSERT INTO assignment_results VALUES ('AS','RQ','T001',?,?,'ASSIGNED',0,90,'{}',?)",
               (f"{DEMO_DAY.isoformat()}T09:00", f"{DEMO_DAY.isoformat()}T10:30", f"{DEMO_DAY.isoformat()}T00:00"))
    db.execute("INSERT INTO jobs VALUES ('JB','CU','AC-DIAG','NORMAL',90,?,?,'East','SCHEDULED')",
               (f"{DEMO_DAY.isoformat()}T09:00", f"{DEMO_DAY.isoformat()}T11:00"))
    db.execute("INSERT INTO schedules VALUES ('JB','T001',?,?,'CONFIRMED',1)",
               (f"{DEMO_DAY.isoformat()}T09:00", f"{DEMO_DAY.isoformat()}T10:30"))
    db.execute("INSERT INTO booking_confirmations VALUES ('AS','RQ','JB','demo-coordinator',?)",
               (f"{DEMO_DAY.isoformat()}T00:00",))
    db.commit()
    plan = create_sick_leave_plan(db, 'T001', f"{DEMO_DAY.isoformat()}T08:30", f"{DEMO_DAY.isoformat()}T12:00")
    assert plan['plan']['unresolved_job_count'] == 1
    app = _coordinator_app(db, monkeypatch)
    app.session_state['recovery_plan_id'] = plan['plan']['plan_id']
    app.run()
    assert not app.exception
    # The Approve button is present but disabled for an unresolved plan.
    approve = next(b for b in app.button if b.label == 'Approve')
    assert approve.disabled is True
    assert 'unresolved' in _visible_text(app).lower()
