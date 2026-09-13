import json

from ..config import settings
from ..schemas.request import StructuredRequest
from .bedrock_client import BedrockClient
from .mock_intake import MockIntake
from .parser import parse_extraction


class IntakeAgent:
    def __init__(self, backend=None):
        self.backend = backend or (BedrockClient() if settings.intake_backend == "bedrock" else MockIntake())

    def structure_request(self, connection, request_id: str) -> StructuredRequest:
        raw = connection.execute("SELECT * FROM customer_requests WHERE request_id=?", (request_id,)).fetchone()
        if raw is None:
            raise ValueError(f"Unknown request_id: {request_id}")
        extracted = parse_extraction(self.backend.extract_request(raw["raw_message"]))
        customer = connection.execute("SELECT * FROM customers WHERE customer_id=?", (raw["customer_id_or_new"],)).fetchone()
        zone = extracted.zone or (customer["zone"] if customer else None)
        rule = connection.execute("SELECT * FROM service_rules WHERE service_rule_id=?", (extracted.service_rule_id,)).fetchone()
        structured = StructuredRequest(request_id=request_id,
            customer_id=customer["customer_id"] if customer else None,
            service_rule_id=rule["service_rule_id"] if rule else None,
            category=rule["category"] if rule else None, subtype=rule["subtype"] if rule else None,
            zone=zone, urgency=extracted.urgency, window_start=extracted.window_start,
            window_end=extracted.window_end, estimated_duration_min=rule["default_duration_min"] if rule else None)
        connection.execute("""INSERT OR REPLACE INTO structured_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (structured.request_id, structured.customer_id, structured.service_rule_id, structured.category,
             structured.subtype, structured.zone, structured.urgency, structured.window_start, structured.window_end,
             structured.estimated_duration_min, json.dumps(structured.missing_fields), int(structured.ready_for_scheduling)))
        connection.commit()
        return structured
