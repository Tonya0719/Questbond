from datetime import datetime, timezone
from uuid import uuid4
import re
import hashlib
import json

from ..orchestration import AgentOrchestrator
from ..llm import MockAgentClient
from ..schemas.agent import AgentResponse, WorkflowStatus
from .photo_service import assess_and_store_photo, store_photo_metadata, validate_photo


def submit_request(connection, raw_message: str, customer_id_or_new: str = "NEW", channel: str = "WEB",
                   contact: dict | None = None, scheduling_context: str = "", idempotency_key: str | None = None,
                   photo: dict | None = None):
    if not raw_message.strip() and not photo:
        raise ValueError("Describe the maintenance issue.")
    if contact:
        if not all(contact.get(key, "").strip() for key in ("name", "email", "apartment")):
            raise ValueError("Enter your name, email, and apartment location.")
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", contact["email"]):
            raise ValueError("Enter a valid email address.")
        if re.search(r"next to|lift lobby|near (?:the )?lift", contact["apartment"], re.I) and not re.search(r"unit\s*\w|#\s*\w", contact["apartment"], re.I):
            raise ValueError("Please provide an identifiable block/street and unit, rather than a nearby landmark.")
    if photo:
        validate_photo(photo)
    photo_fingerprint = hashlib.sha256(photo['data']).hexdigest() if photo else None
    payload_hash = hashlib.sha256(json.dumps({"message": raw_message.strip(), "customer": customer_id_or_new,
        "channel": channel, "contact": contact, "context": scheduling_context,
        "photo": photo_fingerprint}, sort_keys=True).encode()).hexdigest()
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
        stored_message = raw_message.strip() or 'Photo uploaded for visual assessment.'
        connection.execute("INSERT INTO customer_requests VALUES (?,?,?,?,?,?)",
            (request_id, customer_id_or_new, datetime.now(timezone.utc).isoformat(), channel, stored_message, "en"))
        if contact:
            connection.execute("INSERT INTO request_contacts VALUES (?,?,?,?)",
                               (request_id, contact["name"].strip(), contact["email"].strip(), contact["apartment"].strip()))
        connection.execute("INSERT INTO request_submissions VALUES (?,?,?)", (key, request_id, payload_hash))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    photo_context = ''
    effective_description = raw_message.strip()
    if photo:
        if effective_description:
            store_photo_metadata(connection, request_id, photo)
            assessment = None
        else:
            assessment = assess_and_store_photo(connection, request_id, raw_message, photo)
    if photo and assessment:
        canonical = {
            'AC-ROUTINE': 'routine aircon servicing', 'AC-DIAG': 'aircon not cooling',
            'AC-LEAK': 'aircon is leaking', 'PL-LEAK': 'pipe leak',
            'PL-BLOCK': 'drain blockage', 'PL-FIXTURE': 'fixture replacement',
            'EL-REPAIR': 'socket repair', 'EL-TRIP': 'power trip',
            'EL-INSTALL': 'minor electrical installation', 'PA-WALL': 'wall painting',
            'PA-TOUCH': 'painting touch-up', 'CA-DOOR': 'door repair',
            'CA-CABINET': 'cabinet repair', 'MA-CRACK': 'wall crack cement patch',
            'MA-TILE': 'tile repair',
        }.get(assessment['suggested_service_rule_id'], '')
        effective_description = effective_description or canonical or assessment['summary']
        generated = f"Photo agent assessment: {assessment['summary']}"
        if canonical:
            generated += f" Identified request: {canonical}."
        connection.execute("UPDATE customer_requests SET raw_message=? WHERE request_id=?",
                           (raw_message.strip() or generated, request_id))
        connection.commit()
        photo_context = (f"\nUnverified photo assessment: {assessment['summary']} "
                         f"Suggested service rule: {assessment['suggested_service_rule_id'] or 'unclear'}. "
                         f"Photo urgency: {assessment['urgency']}. "
                         f"Safety note: {assessment['safety_note']}")
    agent_message = ((f"Customer-provided booking details: {scheduling_context}\n" if scheduling_context else "")
                     + effective_description + photo_context)
    public_message = raw_message.strip() or 'I uploaded a photo for the agent to assess.'
    orchestrator = (AgentOrchestrator(connection, llm_client=MockAgentClient())
                    if photo and not raw_message.strip() else AgentOrchestrator(connection))
    return orchestrator.run_request(
        request_id, customer_id_or_new, agent_message, customer_message=public_message)


def continue_request(connection, session_id: str, message: str):
    return AgentOrchestrator(connection).continue_session(session_id, message)
