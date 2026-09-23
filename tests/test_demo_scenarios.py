"""Checkpoint 6 — repeatable, synthetic demo scenarios (no manual SQLite editing).

Each test drives one judge-facing demo end to end on the mock backend from a
freshly seeded database. Together they prove the six demos are synthetic and
repeatable, and that displayed explanations are backed by stored evidence.
"""
from datetime import date

from src.demo_scenarios import seed_sick_leave_scenario
from src.orchestration import AgentOrchestrator
from src.llm import MockAgentClient
from src.schemas.agent import WorkflowStatus
from src.services.disruption_service import create_delay_plan
from src.services.request_service import submit_request

DEMO_DAY = date(2030, 1, 20)
CONTACT = {'name': 'Synthetic Resident', 'email': 'demo@example.com', 'apartment': 'Block A, unit #05-12'}
PNG = None  # set lazily to avoid import cost when unused


def _png():
    import base64
    return {'filename': 'leaking-aircon.png', 'media_type': 'image/png', 'data': base64.b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')}


# 1. Normal booking: Intake -> Scheduling -> validated recommendation
def test_demo_normal_booking(db):
    response = AgentOrchestrator(db, MockAgentClient()).run_request(
        'R001', 'C001', 'aircon is leaking East 2025-01-15T10:00 2025-01-15T13:00')
    assert response.workflow_status == WorkflowStatus.RECOMMENDATION_CREATED
    assert [h['handoff_type'] for h in response.handoffs] == ['REQUEST_READY', 'ASSIGNMENT_RECOMMENDED']
    # Displayed message references the actually assigned technician (stored evidence).
    assignment = db.execute("SELECT * FROM assignment_results WHERE request_id='R001' AND decision_status='ASSIGNED'").fetchone()
    alias = db.execute("SELECT name_alias FROM technicians WHERE technician_id=?",
                       (assignment['technician_id'],)).fetchone()['name_alias']
    assert alias in response.result['message']
    assert assignment['scheduled_start'] in response.result['message']


# 2. Clarification: missing field -> no guessing -> same session -> schedule when ready
def test_demo_clarification(db):
    orchestrator = AgentOrchestrator(db, MockAgentClient())
    first = orchestrator.run_request('R010', 'C010', 'toilet blockage South')
    assert first.workflow_status == WorkflowStatus.NEEDS_CLARIFICATION
    assert db.execute("SELECT COUNT(*) FROM assignment_results WHERE request_id='R010'").fetchone()[0] == 0
    second = orchestrator.continue_session(first.session_id, '2025-01-15T13:00 2025-01-15T17:00')
    assert second.session_id == first.session_id
    assert second.workflow_status == WorkflowStatus.RECOMMENDATION_CREATED


# 3. Photo-only intake: blank text + image -> visual assessment -> canonical rule -> scheduling
def test_demo_photo_only(db):
    response = submit_request(db, '', contact=CONTACT,
                              scheduling_context='East 2030-01-20T10:00 2030-01-20T13:00', photo=_png())
    assessment = db.execute('SELECT * FROM photo_assessments WHERE request_id=?',
                            (response.request_id,)).fetchone()
    request = db.execute('SELECT service_rule_id FROM structured_requests WHERE request_id=?',
                         (response.request_id,)).fetchone()
    assert assessment['assessment_source'] == 'mock-demo'
    assert assessment['suggested_service_rule_id'] == request['service_rule_id'] == 'AC-LEAK'
    assert response.workflow_status == WorkflowStatus.RECOMMENDATION_CREATED


# 4. UNAVAILABLE: confirmed jobs -> disruption -> Before/After -> human review/approval
def test_demo_unavailable(db):
    scenario = seed_sick_leave_scenario(db, DEMO_DAY)
    result = AgentOrchestrator(db).run_disruption_recovery(
        scenario['technician_id'], scenario['unavailable_from'], scenario['unavailable_until'])
    assert result['created_session'] is True
    assert result['workflow_status'] == WorkflowStatus.HUMAN_REVIEW_REQUIRED
    plan = result['plan']['plan']
    assert plan['affected_job_count'] == 3 and plan['resolved_job_count'] == 3
    # Before/After evidence exists per job.
    for action in result['plan']['actions']:
        assert action['before_technician'] and action['after_technician']


# 5. DELAYED: near downstream job affected, later job unchanged (minimum change)
def test_demo_delayed_minimum_change(db):
    # Two confirmed T001 jobs: one overlapping the delay, one well after it.
    db.execute("INSERT OR IGNORE INTO customers VALUES ('DC','R','RESIDENTIAL','EMAIL','1','East','any')")
    for jid, start, end in (('NEAR', '09:00', '10:00'), ('LATER', '14:00', '15:00')):
        db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)",
                   (jid, 'DC', 'AC-ROUTINE', 'NORMAL', 60,
                    f'{DEMO_DAY.isoformat()}T08:00', f'{DEMO_DAY.isoformat()}T16:00', 'East', 'SCHEDULED'))
        db.execute("INSERT INTO schedules VALUES (?,?,?,?,?,?)",
                   (jid, 'T001', f'{DEMO_DAY.isoformat()}T{start}', f'{DEMO_DAY.isoformat()}T{end}', 'CONFIRMED', 1))
    db.commit()
    plan = create_delay_plan(db, 'T001', f'{DEMO_DAY.isoformat()}T09:00', 30)
    # Only the near job is reconsidered; the later job is untouched (not in the plan).
    assert plan['plan']['affected_job_count'] == 1
    assert {a['job_id'] for a in plan['actions']} == {'NEAR'}
    assert plan['actions'][0]['action_type'] == 'SHIFT_SAME_TECHNICIAN'


# 6. UNRESOLVED: no valid recovery -> no partial auto-apply
def test_demo_unresolved_blocks_partial_apply(db):
    from src.services.disruption_service import create_sick_leave_plan, approve_plan
    import pytest
    # Only T001 can perform AC-DIAG; disabling others leaves no replacement.
    db.execute("UPDATE technicians SET status='UNAVAILABLE' WHERE technician_id!='T001'")
    db.execute("INSERT OR IGNORE INTO customers VALUES ('UC','R','RESIDENTIAL','EMAIL','1','East','any')")
    db.execute("INSERT INTO jobs VALUES ('UJ','UC','AC-DIAG','NORMAL',90,?,?,'East','SCHEDULED')",
               (f'{DEMO_DAY.isoformat()}T09:00', f'{DEMO_DAY.isoformat()}T11:00'))
    db.execute("INSERT INTO schedules VALUES ('UJ','T001',?,?,'CONFIRMED',1)",
               (f'{DEMO_DAY.isoformat()}T09:00', f'{DEMO_DAY.isoformat()}T10:30'))
    db.commit()
    plan = create_sick_leave_plan(db, 'T001', f'{DEMO_DAY.isoformat()}T08:30', f'{DEMO_DAY.isoformat()}T12:00')
    assert plan['plan']['unresolved_job_count'] == 1
    with pytest.raises(ValueError, match='unresolved'):
        approve_plan(db, plan['plan']['plan_id'], 'demo-coordinator')
    # Nothing applied.
    assert db.execute("SELECT technician_id FROM schedules WHERE job_id='UJ'").fetchone()['technician_id'] == 'T001'


# Repeatability: a fresh seeded DB yields identical deterministic recovery.
def test_demo_repeatable_recovery_is_deterministic(db, tmp_path):
    from src.database import connect
    from src.seed_database import seed_database
    from src.services.disruption_service import create_sick_leave_plan

    def recover(connection):
        scenario = seed_sick_leave_scenario(connection, DEMO_DAY)
        plan = create_sick_leave_plan(connection, scenario['technician_id'],
                                      scenario['unavailable_from'], scenario['unavailable_until'])
        return [a['proposed_technician_id'] for a in plan['actions']]

    first = recover(db)
    other = connect(tmp_path / 'repeat.db')
    seed_database(other)
    second = recover(other)
    other.close()
    assert first == second
