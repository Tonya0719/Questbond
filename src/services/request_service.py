from datetime import datetime, timezone
from uuid import uuid4
import re
import hashlib
import json

from ..orchestration import AgentOrchestrator
from ..schemas.agent import AgentResponse, WorkflowStatus


def submit_request(connection, raw_message: str, customer_id_or_new: str = "NEW", channel: str = "WEB",
                   contact: dict | None = None, scheduling_context: str = "", idempotency_key: str | None = None):
    if not raw_message.strip():
        raise ValueError("Describe the maintenance issue.")
    if contact:
        if not all(contact.get(key, "").strip() for key in ("name", "email", "apartment")):
            raise ValueError("Enter your name, email, and apartment location.")
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", contact["email"]):
            raise ValueError("Enter a valid email address.")
        if re.search(r"next to|lift lobby|near (?:the )?lift", contact["apartment"], re.I) and not re.search(r"unit\s*\w|#\s*\w", contact["apartment"], re.I):
            raise ValueError("Please provide an identifiable block/street and unit, rather than a nearby landmark.")
    payload_hash = hashlib.sha256(json.dumps({"message": raw_message.strip(), "customer": customer_id_or_new,
        "channel": channel, "contact": contact, "context": scheduling_context}, sort_keys=True).encode()).hexdigest()
    key = idempotency_key or uuid4().hex
    connection.execute("BEGIN IMMEDIATE")
    try:
        previous = connection.execute("SELECT * FROM request_submissions WHERE idempotency_key=?", (key,)).fetchone()
        if previous:
            if previous["payload_hash"] != payload_hash:
                raise ValueError("This submission key was used for different details. Start a new request.")
            connection.commit()
            session = connection.execute("SELECT * FROM agent_sessions WHERE request_id=? ORDER BY created_at DESC LIMIT 1",
                                         (previous["request_id"],)).fetchone()
            if not session:
                raise ValueError("This request is already being processed. Please wait before trying again.")
            message = connection.execute("SELECT content FROM agent_messages WHERE session_id=? AND role='assistant' ORDER BY created_at DESC LIMIT 1",
                                         (session["session_id"],)).fetchone()
            return AgentResponse(session_id=session["session_id"], request_id=previous["request_id"],
                workflow_status=WorkflowStatus(session["workflow_status"]),
                message=message["content"] if message else "Your request is already being processed.")
        request_id = f"REQ-{uuid4().hex[:10]}"
        connection.execute("INSERT INTO customer_requests VALUES (?,?,?,?,?,?)",
            (request_id, customer_id_or_new, datetime.now(timezone.utc).isoformat(), channel, raw_message, "en"))
        if contact:
            connection.execute("INSERT INTO request_contacts VALUES (?,?,?,?)",
                               (request_id, contact["name"].strip(), contact["email"].strip(), contact["apartment"].strip()))
        connection.execute("INSERT INTO request_submissions VALUES (?,?,?)", (key, request_id, payload_hash))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    agent_message = (f"Customer-provided booking details: {scheduling_context}\n" if scheduling_context else "") + raw_message
    return AgentOrchestrator(connection).run_request(request_id, customer_id_or_new, agent_message)


def continue_request(connection, session_id: str, message: str):
    return AgentOrchestrator(connection).continue_session(session_id, message)
