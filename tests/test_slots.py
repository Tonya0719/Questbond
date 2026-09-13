from src.scheduling.slots import find_earliest_feasible_slot


def test_slot_search_skips_conflict_in_thirty_minute_steps(db):
    technician = db.execute("SELECT * FROM technicians WHERE technician_id='T001'").fetchone()
    company = db.execute("SELECT * FROM company_profile").fetchone()
    slot = find_earliest_feasible_slot(db, technician, "2025-01-15T08:00", "2025-01-15T12:00", 60, company)
    assert slot[0].isoformat(timespec="minutes") == "2025-01-15T09:00"


def test_job_outside_shift_has_no_slot(db):
    technician = db.execute("SELECT * FROM technicians WHERE technician_id='T003'").fetchone()
    company = db.execute("SELECT * FROM company_profile").fetchone()
    assert find_earliest_feasible_slot(db, technician, "2025-01-15T16:30", "2025-01-15T18:00", 60, company) is None
