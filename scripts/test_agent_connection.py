"""Live agent smoke test using synthetic data in a disposable database."""
from datetime import datetime, timedelta
from pathlib import Path
import sys
import tempfile
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import settings
from src.database import connect
from src.seed_database import seed_database
from src.services.request_service import submit_request
from src.llm.usage import request_usage


def main():
    if settings.llm_backend not in {'local', 'gateway'}:
        print("Configure the local or gateway backend in questbond/.env first.")
        return 1
    key = settings.llm_gateway_api_key if settings.llm_backend == 'gateway' else settings.local_llm_api_key
    if not key or key in {"local", "YOUR_OPENROUTER_KEY"}:
        print("A model API key has not been configured.")
        return 1
    day = (datetime.now(ZoneInfo("Asia/Singapore")) + timedelta(days=1)).date().isoformat()
    with tempfile.TemporaryDirectory() as directory:
        connection = connect(Path(directory) / "smoke.db")
        try:
            seed_database(connection)
            response = submit_request(connection, "The kitchen pipe is leaking", contact={
                "name": "Synthetic Resident", "email": "resident@example.com", "apartment": "Demo Block A"},
                scheduling_context=f"East {day}T10:00 {day}T13:00")
            print("Live model:", settings.llm_model if settings.llm_backend == 'gateway' else settings.local_llm_model)
            print("Workflow:", response.workflow_status.value)
            if response.result:
                assignment = response.result.get("assignment", {})
                print("Technician:", assignment.get("technician_id"))
                print("Validation passed:", response.result.get("validation", {}).get("valid", False))
            print("Audited tool calls:", connection.execute("SELECT COUNT(*) FROM agent_tool_calls").fetchone()[0])
            usage = request_usage(connection, response.request_id)
            print("Model calls:", usage["model_calls"])
            if usage["model_calls"] and usage["priced_calls"] == usage["model_calls"]:
                print(f"Provider-reported run cost: ${usage['cost_usd']:.6f}")
            else:
                print("Run cost: unavailable or partial; not assumed to be zero.")
            return 0 if response.workflow_status.value == "RECOMMENDATION_CREATED" else 1
        except Exception as error:
            # Never print request headers, credentials, remote bodies or tracebacks.
            print("Live agent test failed:", type(error).__name__)
            cause = error.__cause__ or error
            print("Underlying error:", type(cause).__name__)
            if hasattr(cause, "code"):
                print("HTTP status:", cause.code)
            elif hasattr(cause, "reason"):
                print("Connection error type:", type(cause.reason).__name__)
            print("Check network access, key balance, model availability, and tool support.")
            return 1
        finally:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
