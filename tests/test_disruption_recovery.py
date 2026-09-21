from datetime import date

import pytest

from src.demo_scenarios import seed_sick_leave_scenario
from src.services.disruption_service import approve_plan, create_sick_leave_plan


def prepare(db):
    scenario = seed_sick_leave_scenario(db, date(2030, 1, 20))
    return scenario, create_sick_leave_plan(
        db, scenario['technician_id'], scenario['unavailable_from'], scenario['unavailable_until'])


def test_sick_leave_plan_recovers_three_confirmed_visits(db):
    scenario, recovery = prepare(db)
    plan, actions = recovery['plan'], recovery['actions']
    assert plan['affected_job_count'] == 3
    assert plan['resolved_job_count'] == 3
    assert plan['unresolved_job_count'] == 0
    assert [row['job_id'] for row in actions] == scenario['job_ids']
    assert actions[0]['proposed_technician_id'] == 'T003'
    assert actions[1]['proposed_technician_id'] == 'T002'
    assert actions[2]['proposed_technician_id'] == 'T009'
    assert all(row['action_type'] == 'REASSIGN_SAME_TIME' for row in actions)


def test_approval_updates_schedules_and_creates_customer_drafts(db):
    scenario, recovery = prepare(db)
    approved = approve_plan(db, recovery['plan']['plan_id'], 'coordinator-test')
    assert approved['plan']['plan_status'] == 'APPROVED'
    schedules = db.execute(
        f"SELECT * FROM schedules WHERE job_id IN ({','.join('?' for _ in scenario['job_ids'])}) ORDER BY job_id",
        scenario['job_ids']).fetchall()
    assert [row['technician_id'] for row in schedules] == ['T003', 'T002', 'T009']
    notices = db.execute(
        f"SELECT * FROM customer_notifications WHERE job_id IN ({','.join('?' for _ in scenario['job_ids'])}) ORDER BY job_id",
        scenario['job_ids']).fetchall()
    assert len(notices) == 3
    assert all(row['delivery_status'] == 'DRAFT' for row in notices)
    assert all('reported sick' in row['body'] for row in notices)


def test_same_sick_leave_event_is_idempotent(db):
    scenario, first = prepare(db)
    second = create_sick_leave_plan(
        db, scenario['technician_id'], scenario['unavailable_from'], scenario['unavailable_until'])
    assert second['plan']['plan_id'] == first['plan']['plan_id']
    assert db.execute('SELECT COUNT(*) FROM operational_events').fetchone()[0] == 1


def test_stale_plan_does_not_partially_update_schedules(db):
    scenario, recovery = prepare(db)
    db.execute("UPDATE schedules SET scheduled_start='2030-01-20T09:30' WHERE job_id=?", (scenario['job_ids'][0],))
    db.commit()
    with pytest.raises(ValueError, match='schedule changed'):
        approve_plan(db, recovery['plan']['plan_id'], 'coordinator-test')
    rows = db.execute(
        f"SELECT technician_id FROM schedules WHERE job_id IN ({','.join('?' for _ in scenario['job_ids'])}) ORDER BY job_id",
        scenario['job_ids']).fetchall()
    assert [row['technician_id'] for row in rows] == ['T001', 'T001', 'T001']
    assert db.execute('SELECT COUNT(*) FROM customer_notifications').fetchone()[0] == 0
