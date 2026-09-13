import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import settings
from src.database import connect
from src.seed_database import seed_database
from scripts.validate_seed_data import validate_database


def main():
    if settings.db_path.exists():
        raise SystemExit(f"Database already exists: {settings.db_path}. Use reset_db.py to rebuild it.")
    connection = connect()
    try:
        seed_database(connection)
        errors = validate_database(connection)
        if errors:
            raise SystemExit("Seed validation failed:\n- " + "\n- ".join(errors))
    finally:
        connection.close()
    print(f"Initialized {settings.db_path}")


if __name__ == "__main__":
    main()
