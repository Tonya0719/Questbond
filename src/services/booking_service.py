"""Human-owned confirmation; deliberately absent from agent tools."""
from datetime import datetime, timezone
from uuid import uuid4

from ..tools.scheduling_tools import validate_assignment_recommendation
from .triage_service import assess_request


def confirm_recommendation(connection, assignment_id: str, coordinator_id: str):
    if not coordinator_id.strip():
        raise ValueError("A coordinator identity is required.")
    connection.execute("BEGIN IMMEDIATE")
    try:
        previous = connection.execute("SELECT * FROM booking_confirmations WHERE assignment_id=?", (assignment_id,)).fetchone()
        if previous:
            connection.commit()
            return dict(previous)
        assignment = connection.execute("SELECT * FROM assignment_results WHERE assignment_id=?", (assignment_id,)).fetchone()
        if not assignment or assignment["decision_status"] != "ASSIGNED":
            raise ValueError("Only a feasible recommendation can be confirmed.")
        raw = connection.execute("SELECT raw_message FROM customer_requests WHERE request_id=?", (assignment["request_id"],)).fetchone()
        if assess_request(raw["raw_message"])["human_review_required"]:
            raise ValueError("Safety or multiple-issue review is required; this demo cannot confirm the request automatically.")
        if connection.execute("SELECT 1 FROM booking_confirmations WHERE request_id=?", (assignment["request_id"],)).fetchone():
            raise ValueError("This request already has a confirmed booking.")
        validation = validate_assignment_recommendation(connection, assignment_id)
        if not validation["valid"]:
            raise ValueError("Recommendation is stale or invalid: " + ", ".join(validation["violations"]))
        request = connection.execute("SELECT * FROM structured_requests WHERE request_id=?", (assignment["request_id"],)).fetchone()
        customer_id = request["customer_id"]
        if not customer_id or not connection.execute("SELECT 1 FROM customers WHERE customer_id=?", (customer_id,)).fetchone():
            contact = connection.execute("SELECT * FROM request_contacts WHERE request_id=?", (request["request_id"],)).fetchone()
            if not contact:
                raise ValueError("Customer contact details are required before confirming a new customer.")
            customer_id = f"C-{uuid4().hex[:12]}"
            connection.execute("INSERT INTO customers VALUES (?,?,?,?,?,?,?)", (
                customer_id, contact["name"], "RESIDENTIAL", "EMAIL", "", request["zone"], ""))
            connection.execute("UPDATE structured_requests SET customer_id=? WHERE request_id=?", (customer_id, request["request_id"]))
        job_id = f"WO-{uuid4().hex[:10]}"
        connection.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)", (
            job_id, customer_id, request["service_rule_id"], request["urgency"], request["estimated_duration_min"],
            request["window_start"], request["window_end"], request["zone"], "SCHEDULED"))
        connection.execute("INSERT INTO schedules VALUES (?,?,?,?,?,?)", (
            job_id, assignment["technician_id"], assignment["scheduled_start"], assignment["scheduled_end"], "CONFIRMED", 0))
        now = datetime.now(timezone.utc).isoformat()
        connection.execute("INSERT INTO booking_confirmations VALUES (?,?,?,?,?)", (
            assignment_id, request["request_id"], job_id, coordinator_id, now))
        connection.commit()
        return {"assignment_id": assignment_id, "request_id": request["request_id"], "job_id": job_id,
                "coordinator_id": coordinator_id, "confirmed_at": now}
    except Exception:
        connection.rollback()
        raise


def notification_draft(connection, request_id: str):
    row = connection.execute("""SELECT bc.job_id, rc.email, rc.name, rc.apartment, s.scheduled_start,
        s.scheduled_end, t.name_alias, sr.subtype FROM booking_confirmations bc
        JOIN schedules s ON s.job_id=bc.job_id JOIN technicians t ON t.technician_id=s.technician_id
        JOIN structured_requests r ON r.request_id=bc.request_id JOIN service_rules sr ON sr.service_rule_id=r.service_rule_id
        LEFT JOIN request_contacts rc ON rc.request_id=bc.request_id WHERE bc.request_id=?""", (request_id,)).fetchone()
    if not row:
        return None
    return (f"To: {row['email'] or '(demo customer)'}\nSubject: Maintenance visit confirmed — {row['job_id']}\n\n"
            f"Hello {row['name'] or 'Customer'},\n\nYour {row['subtype']} visit has been scheduled.\n"
            f"Location: {row['apartment'] or '(on file)'}\nTechnician: {row['name_alias']}\n"
            f"Appointment: {row['scheduled_start']} to {row['scheduled_end']} (Singapore time)\n"
            f"Work order: {row['job_id']}\n\nYour maintenance coordination team")
