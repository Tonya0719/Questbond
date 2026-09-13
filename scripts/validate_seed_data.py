import sys
from collections import Counter, defaultdict
from datetime import datetime, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.database import connect
from src.scheduling.conflicts import intervals_overlap
from src.scheduling.eligibility import has_required_certifications, has_required_skills
from src.scheduling.workload import get_assigned_workload


def validate_database(connection):
    errors = []
    expected = {"company_profile": 1, "service_rules": 9, "technicians": 8, "customers": 12,
                "jobs": 16, "schedules": 16, "customer_requests": 10}
    for table, count in expected.items():
        actual = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if actual != count:
            errors.append(f"{table}: expected {count} records, found {actual}")
    for table, id_column in (("service_rules", "service_rule_id"), ("technicians", "technician_id"),
                             ("customers", "customer_id"), ("jobs", "job_id"),
                             ("customer_requests", "request_id")):
        ids = [r[0] for r in connection.execute(f"SELECT {id_column} FROM {table}")]
        duplicates = [key for key, value in Counter(ids).items() if value > 1]
        if duplicates:
            errors.append(f"{table}: duplicate IDs {duplicates}")
    schedules_by_tech = defaultdict(list)
    for schedule in connection.execute("SELECT * FROM schedules"):
        job = connection.execute("SELECT * FROM jobs WHERE job_id=?", (schedule["job_id"],)).fetchone()
        tech = connection.execute("SELECT * FROM technicians WHERE technician_id=?", (schedule["technician_id"],)).fetchone()
        if not job or not tech:
            errors.append(f"schedule {schedule['job_id']}: invalid job or technician reference")
            continue
        start, end = datetime.fromisoformat(schedule["scheduled_start"]), datetime.fromisoformat(schedule["scheduled_end"])
        if start >= end:
            errors.append(f"schedule {schedule['job_id']}: start is not before end")
        if not (time.fromisoformat(tech["shift_start"]) <= start.time() and end.time() <= time.fromisoformat(tech["shift_end"])):
            errors.append(f"schedule {schedule['job_id']}: outside technician shift")
        if int((end - start).total_seconds() / 60) != job["estimated_duration_min"]:
            errors.append(f"schedule {schedule['job_id']}: duration does not match job")
        rule = connection.execute("SELECT * FROM service_rules WHERE service_rule_id=?", (job["service_rule_id"],)).fetchone()
        if not rule:
            errors.append(f"job {job['job_id']}: missing service rule")
        elif not has_required_skills(tech, rule):
            errors.append(f"schedule {schedule['job_id']}: technician lacks required skill")
        elif not has_required_certifications(tech, rule):
            errors.append(f"schedule {schedule['job_id']}: technician lacks certification")
        for other_start, other_end, other_job in schedules_by_tech[tech["technician_id"]]:
            if intervals_overlap(start, end, other_start, other_end):
                errors.append(f"technician {tech['technician_id']}: overlapping {other_job} and {schedule['job_id']}")
        schedules_by_tech[tech["technician_id"]].append((start, end, schedule["job_id"]))
    for tech in connection.execute("SELECT * FROM technicians"):
        dates = {row[0] for row in connection.execute("SELECT DISTINCT date(scheduled_start) FROM schedules WHERE technician_id=?", (tech["technician_id"],))}
        for date in dates:
            if get_assigned_workload(connection, tech["technician_id"], date) > tech["max_workload_min"]:
                errors.append(f"technician {tech['technician_id']}: workload exceeds capacity on {date}")
    for request in connection.execute("SELECT * FROM structured_requests WHERE service_rule_id IS NOT NULL"):
        rule = connection.execute("SELECT * FROM service_rules WHERE service_rule_id=?", (request["service_rule_id"],)).fetchone()
        if not rule or (request["category"], request["subtype"]) != (rule["category"], rule["subtype"]):
            errors.append(f"structured request {request['request_id']}: category/subtype disagree with service rule")
    return errors


def main():
    connection = connect()
    try:
        errors = validate_database(connection)
    finally:
        connection.close()
    if errors:
        print("Validation failed:\n- " + "\n- ".join(errors))
        return 1
    print("Seed data validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
