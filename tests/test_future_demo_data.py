from src.demo_scenarios import seed_future_workforce
from src.scheduling.assignment_engine import assign_technician
from src.services.availability_service import next_available_offer


def add_request(db, request_id, service_rule, start, end, duration):
    db.execute("INSERT INTO customer_requests VALUES (?,?,?,?,?,?)",
               (request_id, 'NEW', '2026-09-21T08:00:00', 'WEB', 'Synthetic availability test', 'en'))
    rule = db.execute('SELECT * FROM service_rules WHERE service_rule_id=?', (service_rule,)).fetchone()
    db.execute("INSERT INTO structured_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
        request_id, None, service_rule, rule['category'], rule['subtype'], 'Central', 'NORMAL',
        start, end, duration, '[]', 1))
    db.commit()


def test_future_dataset_has_twenty_days_and_six_trades(db):
    summary = seed_future_workforce(db)
    assert summary['start_date'] == '2026-09-21'
    assert summary['end_date'] == '2026-10-10'
    assert summary['capacity_cases'] == 40
    assert summary['scheduled_jobs'] >= 120
    assert summary['technicians'] == 18
    assert summary['customers'] == 60
    assert summary['domains'] == 6
    categories = {row[0] for row in db.execute('SELECT DISTINCT category FROM service_rules')}
    assert {'Air-conditioning', 'Plumbing', 'Electrical', 'Painting', 'Carpentry',
            'Masonry / cement'}.issubset(categories)
    assert db.execute("SELECT COUNT(DISTINCT work_date) FROM demo_capacity_cases").fetchone()[0] == 20
    assert not db.execute("SELECT 1 FROM operational_events WHERE event_id LIKE 'FUT-CAP-%'").fetchone()


def test_every_daily_capacity_case_is_backed_by_real_appointments(db):
    seed_future_workforce(db)
    cases = db.execute('''SELECT d.*, s.default_duration_min FROM demo_capacity_cases d
        JOIN service_rules s ON s.service_rule_id=d.service_rule_id ORDER BY d.work_date, d.window_start''').fetchall()
    assert len(cases) == 40
    for index, case in enumerate(cases):
        request_id = f'CAPACITY-TEST-{index:02d}'
        add_request(db, request_id, case['service_rule_id'], case['window_start'], case['window_end'],
                    case['default_duration_min'])
        result = assign_technician(request_id, db)
        assert result.decision_status == 'NO_FEASIBLE_TECHNICIAN'


def test_full_window_produces_a_next_available_offer(db):
    seed_future_workforce(db)
    case = db.execute("SELECT * FROM demo_capacity_cases WHERE work_date='2026-09-22' ORDER BY window_start LIMIT 1").fetchone()
    rule = db.execute('SELECT * FROM service_rules WHERE service_rule_id=?', (case['service_rule_id'],)).fetchone()
    add_request(db, 'NEXT-OFFER', case['service_rule_id'], case['window_start'], case['window_end'],
                rule['default_duration_min'])
    assert assign_technician('NEXT-OFFER', db).decision_status == 'NO_FEASIBLE_TECHNICIAN'
    offer = next_available_offer(db, 'NEXT-OFFER')
    assert offer
    assert offer['scheduled_start'] >= case['window_end']
    assert offer['scheduled_end'] > offer['scheduled_start']


def test_future_dataset_is_idempotent(db):
    first = seed_future_workforce(db)
    second = seed_future_workforce(db)
    assert second == first
    assert db.execute("SELECT COUNT(*) FROM demo_capacity_cases").fetchone()[0] == 40
    assert db.execute("SELECT COUNT(*) FROM jobs WHERE job_id LIKE 'FUT-%'").fetchone()[0] == first['scheduled_jobs']
