"""Seed data for video shot 3 (Coordinator candidate-evaluation table).

Submits one AC-LEAK request that runs intake + scheduling on the mock backend,
so the coordinator detail shows a candidate table with qualified technicians and
excluded ones (certification / skill mismatches). Idempotent via a fixed key.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.database import connect, create_schema
from src.services.request_service import submit_request


def main():
    connection = connect()
    create_schema(connection)
    tomorrow = datetime.now(ZoneInfo("Asia/Singapore")).date() + timedelta(days=2)
    start = f"{tomorrow.isoformat()}T10:00"
    end = f"{tomorrow.isoformat()}T13:00"
    response = submit_request(
        connection,
        "The aircon is leaking water in the living room",
        contact={"name": "Demo Resident", "email": "demo.shot3@example.com", "apartment": "Block C, unit 12-08"},
        scheduling_context=f"East {start} {end}",
        idempotency_key="VIDEO-SHOT3-AC-LEAK",
    )
    print("request_id:", response.request_id)
    print("workflow_status:", response.workflow_status.value)
    row = connection.execute(
        "SELECT technician_id, decision_status FROM assignment_results WHERE request_id=? "
        "ORDER BY created_at DESC LIMIT 1", (response.request_id,)).fetchone()
    print("assignment:", dict(row) if row else None)
    connection.close()


if __name__ == "__main__":
    main()
