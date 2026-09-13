import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database import connect
from src.seed_database import seed_database


@pytest.fixture
def db(tmp_path):
    connection = connect(tmp_path / "test.db")
    seed_database(connection)
    yield connection
    connection.close()
