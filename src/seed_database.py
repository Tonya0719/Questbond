import csv
import json
from pathlib import Path

from .database import create_schema
from .intake import IntakeAgent

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "runtime" / "seed"


def _rows(name):
    with (SEED_DIR / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def seed_database(connection):
    create_schema(connection)
    profile = json.loads((SEED_DIR / "company_profile.json").read_text(encoding="utf-8"))
    connection.execute("INSERT INTO company_profile VALUES (?,?,?,?,?)", tuple(profile.values()))
    specs = [
        ("service_rules.csv", "service_rules", ["default_duration_min"]),
        ("technicians.csv", "technicians", ["max_workload_min"]),
        ("customers.csv", "customers", []),
        ("jobs_current.csv", "jobs", ["estimated_duration_min"]),
        ("schedule_current.csv", "schedules", ["customer_confirmed"]),
        ("customer_requests.csv", "customer_requests", []),
    ]
    for filename, table, integer_fields in specs:
        for row in _rows(filename):
            for field in integer_fields:
                row[field] = int(row[field])
            placeholders = ",".join("?" for _ in row)
            connection.execute(f"INSERT INTO {table} ({','.join(row)}) VALUES ({placeholders})", tuple(row.values()))
    connection.commit()
    agent = IntakeAgent()
    for row in connection.execute("SELECT request_id FROM customer_requests").fetchall():
        agent.structure_request(connection, row["request_id"])
