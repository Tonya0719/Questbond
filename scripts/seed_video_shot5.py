"""Seed data for video shot 5 (Coordinator Recovery Plans, PROPOSED state).

Seeds the sick-leave scenario (Alex has three confirmed visits, then reports
sick) and builds a PROPOSED recovery plan on the deterministic path, so the
coordinator "Recovery Plans" section shows the governance columns (technician
changed / time changed / customer appointment changed / approval required /
reasons) while the schedule is still unmutated. Idempotent: the same event
reuses the same plan.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.database import connect, create_schema
from src.demo_scenarios import seed_sick_leave_scenario
from src.services.disruption_service import create_sick_leave_plan


def main():
    connection = connect()
    create_schema(connection)
    scenario = seed_sick_leave_scenario(connection)
    recovery = create_sick_leave_plan(
        connection, scenario["technician_id"],
        scenario["unavailable_from"], scenario["unavailable_until"],
        "Sick leave reported before the first appointment")
    plan = recovery["plan"]
    print("technician:", scenario["technician"], scenario["technician_id"])
    print("plan_id:", plan["plan_id"], "status:", plan["plan_status"])
    print("affected:", plan["affected_job_count"],
          "resolved:", plan["resolved_job_count"],
          "unresolved:", plan["unresolved_job_count"])
    print("requires_human_approval:", plan.get("requires_human_approval"))
    connection.close()


if __name__ == "__main__":
    main()
