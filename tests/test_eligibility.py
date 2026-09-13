from src.scheduling.eligibility import eligibility_reasons, has_required_certifications, has_required_skills


def test_skill_and_certification_matching(db):
    rule = db.execute("SELECT * FROM service_rules WHERE service_rule_id='AC-DIAG'").fetchone()
    qualified = db.execute("SELECT * FROM technicians WHERE technician_id='T001'").fetchone()
    uncertified = db.execute("SELECT * FROM technicians WHERE technician_id='T003'").fetchone()
    assert has_required_skills(qualified, rule)
    assert has_required_certifications(qualified, rule)
    assert "CERTIFICATION_MISMATCH" in eligibility_reasons(uncertified, rule)


def test_unavailable_status_excluded(db):
    rule = db.execute("SELECT * FROM service_rules WHERE service_rule_id='EL-REPAIR'").fetchone()
    tech = db.execute("SELECT * FROM technicians WHERE technician_id='T008'").fetchone()
    assert "STATUS_UNAVAILABLE" in eligibility_reasons(tech, rule)
