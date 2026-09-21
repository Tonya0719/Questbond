import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.database import connect, create_schema
from src.demo_scenarios import seed_sick_leave_scenario


def main():
    connection = connect()
    try:
        create_schema(connection)
        scenario = seed_sick_leave_scenario(connection)
    finally:
        connection.close()
    print(f"Prepared {scenario['scenario']} for {scenario['technician']} from "
          f"{scenario['unavailable_from']} to {scenario['unavailable_until']}.")


if __name__ == '__main__':
    main()
