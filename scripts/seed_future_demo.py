import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.database import connect, create_schema
from src.demo_scenarios import seed_future_workforce


def main():
    connection = connect()
    try:
        create_schema(connection)
        summary = seed_future_workforce(connection)
    finally:
        connection.close()
    print(f"Loaded {summary['scheduled_jobs']} jobs, {summary['technicians']} technicians and "
          f"{summary['customers']} synthetic customers from {summary['start_date']} to {summary['end_date']}. "
          f"Created {summary['capacity_cases']} fully booked customer test cases.")


if __name__ == '__main__':
    main()
