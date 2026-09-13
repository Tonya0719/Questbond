from datetime import datetime, timezone
from uuid import uuid4

from ..orchestration import AgentOrchestrator


def submit_request(connection, raw_message: str, customer_id_or_new: str = "NEW", channel: str = "WEB"):
    request_id = f"REQ-{uuid4().hex[:10]}"
    connection.execute("INSERT INTO customer_requests VALUES (?,?,?,?,?,?)",
        (request_id, customer_id_or_new, datetime.now(timezone.utc).isoformat(), channel, raw_message, "en"))
    connection.commit()
    return AgentOrchestrator(connection).run_request(request_id, customer_id_or_new, raw_message)


def continue_request(connection, session_id: str, message: str):
    return AgentOrchestrator(connection).continue_session(session_id, message)
