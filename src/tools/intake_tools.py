from __future__ import annotations

import json
import re
from typing import Optional

from ..schemas.request import StructuredRequest


def get_customer_context(connection, customer_id: str) -> dict:
    customer = connection.execute("SELECT * FROM customers WHERE customer_id=?", (customer_id,)).fetchone()
    if not customer:
        return {"found": False, "customer_id": customer_id}
    return {"found": True, "customer_id": customer["customer_id"], "zone": customer["zone"],
            "preferred_time": customer["preferred_time"], "customer_type": customer["customer_type"]}


def lookup_service_rules(connection, query: str) -> dict:
    terms = {word for word in query.lower().replace("/", " ").replace("-", " ").split() if len(word) > 2}
    aliases = {
        "aircon": {"air-conditioning"}, "cooling": {"cooling", "diagnosis"}, "leaking": {"leakage", "repair"},
        "leak": {"leakage", "repair"}, "tap": {"tap", "leakage"}, "pipe": {"pipe", "leakage"},
        "drain": {"drain", "blockage"}, "toilet": {"toilet", "blockage"}, "blocked": {"blockage"},
        "socket": {"socket", "repair"}, "switch": {"switch", "repair"}, "light": {"light", "repair"},
        "power": {"power", "trip"}, "trip": {"power", "trip"}, "installation": {"installation"},
        "servicing": {"servicing"}, "service": {"servicing"}, "fixture": {"fixture", "replacement"},
    }
    expanded = set(terms)
    for term in terms:
        expanded.update(aliases.get(term, set()))
    matches = []
    for rule in connection.execute("SELECT * FROM service_rules ORDER BY service_rule_id"):
        text = f"{rule['service_rule_id']} {rule['category']} {rule['subtype']}".lower().replace("/", " ").replace("-", " ")
        score = sum(1 for term in expanded if term in text)
        if score:
            matches.append({"service_rule_id": rule["service_rule_id"], "category": rule["category"],
                            "subtype": rule["subtype"], "score": score})
    matches.sort(key=lambda item: (-item["score"], item["service_rule_id"]))
    return {"matches": matches[:5]}


def save_structured_request(connection, request_id: str, customer_id: Optional[str] = None,
                            service_rule_id: Optional[str] = None, zone: Optional[str] = None,
                            urgency: str = "NORMAL", window_start: Optional[str] = None,
                            window_end: Optional[str] = None) -> dict:
    raw = connection.execute("SELECT * FROM customer_requests WHERE request_id=?", (request_id,)).fetchone()
    if raw is None:
        raise ValueError(f"Unknown request_id: {request_id}")
    messages = connection.execute("""SELECT m.content FROM agent_messages m JOIN agent_sessions s ON s.session_id=m.session_id
        WHERE s.request_id=? AND m.role='user' ORDER BY m.created_at""", (request_id,)).fetchall()
    text = " ".join(row["content"] for row in messages) or raw["raw_message"]
    # Vague words are not evidence for exact timestamps. Explicit booking-form
    # windows or a later clarification supply the required evidence.
    explicit_iso = re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", text)
    clock_times = re.findall(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", text, re.I)
    if re.search(r"\b(?:sometime|later|afternoon|whenever)\b", text, re.I) and len(explicit_iso) < 2 and len(clock_times) < 2:
        window_start = window_end = None
    rule = None
    if service_rule_id:
        rule = connection.execute("SELECT * FROM service_rules WHERE service_rule_id=?", (service_rule_id,)).fetchone()
        if rule is None:
            raise ValueError(f"Unknown service_rule_id: {service_rule_id}")
    structured = StructuredRequest(request_id=request_id, customer_id=customer_id,
        service_rule_id=rule["service_rule_id"] if rule else None,
        category=rule["category"] if rule else None, subtype=rule["subtype"] if rule else None,
        zone=zone, urgency=urgency, window_start=window_start, window_end=window_end,
        estimated_duration_min=rule["default_duration_min"] if rule else None)
    if structured.window_start and structured.window_end and structured.window_start >= structured.window_end:
        raise ValueError("window_start must be before window_end")
    connection.execute("INSERT OR REPLACE INTO structured_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (structured.request_id, structured.customer_id, structured.service_rule_id, structured.category,
         structured.subtype, structured.zone, structured.urgency, structured.window_start, structured.window_end,
         structured.estimated_duration_min, json.dumps(structured.missing_fields), int(structured.ready_for_scheduling)))
    connection.commit()
    return structured.model_dump()


def get_request_status(connection, request_id: str) -> dict:
    request = connection.execute("SELECT * FROM structured_requests WHERE request_id=?", (request_id,)).fetchone()
    if not request:
        return {"request_id": request_id, "found": False, "ready_for_scheduling": False,
                "missing_fields": ["structured_request"]}
    result = dict(request)
    result["found"] = True
    result["ready_for_scheduling"] = bool(result["ready_for_scheduling"])
    result["missing_fields"] = json.loads(result["missing_fields"])
    return result
