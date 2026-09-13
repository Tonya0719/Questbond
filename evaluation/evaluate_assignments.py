import csv
from pathlib import Path

from src.scheduling.assignment_engine import assign_technician


def _create_variant(connection, request_id: str):
    source = connection.execute("SELECT * FROM structured_requests WHERE request_id='R001'").fetchone()
    raw = connection.execute("SELECT * FROM customer_requests WHERE request_id='R001'").fetchone()
    connection.execute("INSERT INTO customer_requests VALUES (?,?,?,?,?,?)",
        (request_id, raw["customer_id_or_new"], raw["received_at"], raw["channel"], raw["raw_message"], raw["language"]))
    values = list(source)
    values[0] = request_id
    if request_id == "E-NOFEAS":
        values[7], values[8] = "2025-01-15T17:30", "2025-01-15T18:00"
    connection.execute("INSERT INTO structured_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", values)
    if request_id == "E-WORKLOAD":
        connection.execute("UPDATE technicians SET max_workload_min=200 WHERE technician_id='T001'")
    connection.commit()


def evaluate_assignments(connection, ground_truth_path: Path):
    failures = []
    with ground_truth_path.open(newline="", encoding="utf-8") as handle:
        for expected in csv.DictReader(handle):
            request_id = expected["request_id"]
            if request_id.startswith("E-"):
                _create_variant(connection, request_id)
            actual = assign_technician(request_id, connection)
            comparisons = {
                "decision_status": expected["decision_status"],
                "technician_id": expected["expected_technician"] or None,
                "scheduled_start": expected["expected_start"] or None,
                "scheduled_end": expected["expected_end"] or None,
            }
            for field, value in comparisons.items():
                if getattr(actual, field) != value:
                    failures.append(f"{request_id} {field}: expected {value!r}, got {getattr(actual, field)!r}")
    return failures
