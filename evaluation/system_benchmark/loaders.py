"""Load versioned benchmark fixtures, cases and ground truth.

The base fixtures are seeded into an isolated in-memory (or temp) SQLite database
using the product's schema. Ground truth is loaded separately and is only used by
metrics/suite comparison code — never injected into runtime decision logic.
"""
from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from src.database import connect, create_schema

from . import config

# Integer columns per fixture table (mirrors src/seed_database.py conventions).
_FIXTURE_SPECS = [
    ("service_rules.csv", "service_rules", ["default_duration_min"]),
    ("technicians.csv", "technicians", ["max_workload_min"]),
    ("customers.csv", "customers", []),
    ("jobs.csv", "jobs", ["estimated_duration_min"]),
    ("schedules.csv", "schedules", ["customer_confirmed"]),
]


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def seed_base_fixtures(connection: sqlite3.Connection) -> None:
    """Create the product schema and load the fixed synthetic operational world."""
    create_schema(connection)
    profile = json.loads((config.FIXTURES_DIR / "company_profile.json").read_text(encoding="utf-8"))
    connection.execute("INSERT INTO company_profile VALUES (?,?,?,?,?)", tuple(profile.values()))
    for filename, table, integer_fields in _FIXTURE_SPECS:
        for row in _read_csv(config.FIXTURES_DIR / filename):
            for field in integer_fields:
                row[field] = int(row[field])
            placeholders = ",".join("?" for _ in row)
            connection.execute(f"INSERT INTO {table} ({','.join(row)}) VALUES ({placeholders})",
                               tuple(row.values()))
    _seed_confirmed_bookings(connection)
    connection.commit()


def _seed_confirmed_bookings(connection: sqlite3.Connection) -> None:
    """Synthesise the request→confirmation chain for every CONFIRMED schedule.

    In production, a confirmed job always originates from a customer request. The
    benchmark mirrors that so the orchestrator's disruption path can anchor an
    event session to a real request. This is deterministic and versioned via the
    schedules fixture; no random data is generated.
    """
    confirmed = connection.execute(
        """SELECT s.job_id, j.customer_id, j.service_rule_id, j.priority, j.estimated_duration_min,
                  j.window_start, j.window_end, j.zone, s.technician_id, s.scheduled_start, s.scheduled_end,
                  sr.category, sr.subtype
           FROM schedules s JOIN jobs j ON j.job_id=s.job_id
           JOIN service_rules sr ON sr.service_rule_id=j.service_rule_id
           WHERE s.assignment_status='CONFIRMED' ORDER BY s.job_id""").fetchall()
    for row in confirmed:
        job_id = row["job_id"]
        request_id = f"REQ-{job_id}"
        assignment_id = f"ASG-{job_id}"
        connection.execute("INSERT INTO customer_requests VALUES (?,?,?,?,?,?)",
                           (request_id, row["customer_id"], "2030-03-01T00:00", "WEB",
                            f"confirmed {row['subtype']}", "en"))
        connection.execute("INSERT INTO structured_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
            request_id, row["customer_id"], row["service_rule_id"], row["category"], row["subtype"],
            row["zone"], row["priority"], row["window_start"], row["window_end"],
            row["estimated_duration_min"], "[]", 1))
        connection.execute("INSERT INTO request_contacts VALUES (?,?,?,?)",
                           (request_id, "Bench Resident", f"{job_id.lower()}@example.com", "Unit 01"))
        connection.execute("INSERT INTO assignment_results VALUES (?,?,?,?,?,?,?,?,?,?)", (
            assignment_id, request_id, row["technician_id"], row["scheduled_start"], row["scheduled_end"],
            "ASSIGNED", 0, row["estimated_duration_min"], "{}", "2030-03-01T00:00"))
        connection.execute("INSERT INTO booking_confirmations VALUES (?,?,?,?,?)",
                           (assignment_id, request_id, job_id, "bench-coordinator", "2030-03-01T00:00"))


def new_world(db_path: Path | None = None) -> sqlite3.Connection:
    """Return an isolated connection seeded with the base fixtures.

    Defaults to a true in-memory database so benchmark runs never touch the
    product DB and never create stray files.
    """
    if db_path is None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
    else:
        connection = connect(db_path)
    seed_base_fixtures(connection)
    return connection


def load_cases() -> list[dict]:
    return _read_csv(config.CASES_CSV)


def load_ground_truth() -> dict[str, dict[str, dict]]:
    """Load each suite's GT keyed by case_id. Robustness GT is inlined in cases.csv."""
    truth: dict[str, dict[str, dict]] = {}
    for suite, path in config.GROUND_TRUTH_FILES.items():
        rows = _read_csv(path)
        truth[suite] = {row["case_id"]: row for row in rows}
    return truth


def load_live_subset() -> list[dict]:
    if not config.LIVE_SUBSET_CSV.exists():
        return []
    return _read_csv(config.LIVE_SUBSET_CSV)
