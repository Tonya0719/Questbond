import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.evaluate_assignments import evaluate_assignments
from evaluation.evaluate_requests import evaluate_requests
from src.database import connect
from src.seed_database import seed_database


def main():
    eval_dir = ROOT / "data" / "evaluation"
    with tempfile.TemporaryDirectory() as directory:
        connection = connect(Path(directory) / "evaluation.db")
        try:
            seed_database(connection)
            failures = evaluate_requests(connection, eval_dir / "request_ground_truth.csv")
            failures += evaluate_assignments(connection, eval_dir / "assignment_ground_truth.csv")
        finally:
            connection.close()
    if failures:
        print("Evaluation failed:\n- " + "\n- ".join(failures))
        return 1
    print("Evaluation passed: request extraction and deterministic assignments match ground truth.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
