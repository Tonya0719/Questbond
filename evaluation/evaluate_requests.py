import csv
from pathlib import Path


def evaluate_requests(connection, ground_truth_path: Path):
    failures = []
    with ground_truth_path.open(newline="", encoding="utf-8") as handle:
        for expected in csv.DictReader(handle):
            actual = connection.execute("SELECT * FROM structured_requests WHERE request_id=?", (expected["request_id"],)).fetchone()
            checks = {
                "category": expected["expected_category"], "subtype": expected["expected_subtype"],
                "zone": expected["expected_location"], "urgency": expected["expected_urgency"],
            }
            for field, value in checks.items():
                if (actual[field] or "") != value:
                    failures.append(f"{expected['request_id']} {field}: expected {value!r}, got {actual[field]!r}")
            expected_ready = expected["ready_for_scheduling"].lower() == "true"
            if bool(actual["ready_for_scheduling"]) != expected_ready:
                failures.append(f"{expected['request_id']} readiness mismatch")
    return failures
