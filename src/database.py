from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import settings

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS company_profile (
 company_id TEXT PRIMARY KEY, business_type TEXT NOT NULL, operating_start TEXT NOT NULL,
 operating_end TEXT NOT NULL, dispatch_policy TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS service_rules (
 service_rule_id TEXT PRIMARY KEY, category TEXT NOT NULL, subtype TEXT NOT NULL,
 required_skills TEXT NOT NULL, required_certifications TEXT NOT NULL,
 default_duration_min INTEGER NOT NULL CHECK(default_duration_min > 0),
 default_priority TEXT NOT NULL, required_customer_information TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS technicians (
 technician_id TEXT PRIMARY KEY, name_alias TEXT NOT NULL, skills TEXT NOT NULL,
 certifications TEXT NOT NULL, shift_start TEXT NOT NULL, shift_end TEXT NOT NULL,
 status TEXT NOT NULL, current_zone TEXT NOT NULL,
 max_workload_min INTEGER NOT NULL CHECK(max_workload_min >= 0));
CREATE TABLE IF NOT EXISTS customers (
 customer_id TEXT PRIMARY KEY, name_alias TEXT NOT NULL, customer_type TEXT NOT NULL,
 contact_channel TEXT NOT NULL, postal_sector TEXT NOT NULL, zone TEXT NOT NULL,
 preferred_time TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (
 job_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(customer_id),
 service_rule_id TEXT NOT NULL REFERENCES service_rules(service_rule_id), priority TEXT NOT NULL,
 estimated_duration_min INTEGER NOT NULL, window_start TEXT NOT NULL, window_end TEXT NOT NULL,
 zone TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS schedules (
 job_id TEXT PRIMARY KEY REFERENCES jobs(job_id), technician_id TEXT NOT NULL REFERENCES technicians(technician_id),
 scheduled_start TEXT NOT NULL, scheduled_end TEXT NOT NULL,
 assignment_status TEXT NOT NULL, customer_confirmed INTEGER NOT NULL,
 CHECK(scheduled_start < scheduled_end));
CREATE TABLE IF NOT EXISTS customer_requests (
 request_id TEXT PRIMARY KEY, customer_id_or_new TEXT NOT NULL, received_at TEXT NOT NULL,
 channel TEXT NOT NULL, raw_message TEXT NOT NULL, language TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS structured_requests (
 request_id TEXT PRIMARY KEY REFERENCES customer_requests(request_id), customer_id TEXT,
 service_rule_id TEXT REFERENCES service_rules(service_rule_id), category TEXT, subtype TEXT, zone TEXT,
 urgency TEXT, window_start TEXT, window_end TEXT, estimated_duration_min INTEGER,
 missing_fields TEXT NOT NULL, ready_for_scheduling INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS assignment_results (
 assignment_id TEXT PRIMARY KEY, request_id TEXT NOT NULL REFERENCES structured_requests(request_id),
 technician_id TEXT REFERENCES technicians(technician_id), scheduled_start TEXT, scheduled_end TEXT,
 decision_status TEXT NOT NULL CHECK(decision_status IN ('ASSIGNED','NEEDS_CLARIFICATION','NO_FEASIBLE_TECHNICIAN')),
 workload_before INTEGER, workload_after INTEGER, recommendation_reason TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_sessions (
 session_id TEXT PRIMARY KEY, request_id TEXT NOT NULL REFERENCES customer_requests(request_id),
 customer_id TEXT, current_agent TEXT NOT NULL, workflow_status TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_messages (
 message_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES agent_sessions(session_id),
 role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS customer_messages (
 message_id TEXT PRIMARY KEY REFERENCES agent_messages(message_id),
 content TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_handoffs (
 handoff_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES agent_sessions(session_id),
 source_agent TEXT NOT NULL, target_agent TEXT NOT NULL, handoff_type TEXT NOT NULL,
 request_id TEXT, assignment_id TEXT, payload_json TEXT NOT NULL, evidence_json TEXT NOT NULL,
 created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_tool_calls (
 tool_call_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES agent_sessions(session_id),
 agent_name TEXT NOT NULL, tool_name TEXT NOT NULL, input_json TEXT NOT NULL,
 output_json TEXT NOT NULL, execution_status TEXT NOT NULL, duration_ms INTEGER NOT NULL,
 created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS request_contacts (
 request_id TEXT PRIMARY KEY REFERENCES customer_requests(request_id),
 name TEXT NOT NULL, email TEXT NOT NULL, apartment TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS booking_confirmations (
 assignment_id TEXT PRIMARY KEY REFERENCES assignment_results(assignment_id),
 request_id TEXT NOT NULL UNIQUE REFERENCES customer_requests(request_id),
 job_id TEXT NOT NULL UNIQUE REFERENCES jobs(job_id),
 coordinator_id TEXT NOT NULL, confirmed_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS request_submissions (
 idempotency_key TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE REFERENCES customer_requests(request_id),
 payload_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS request_triage (
 request_id TEXT PRIMARY KEY REFERENCES customer_requests(request_id),
 hazard_flags TEXT NOT NULL, injection_flag INTEGER NOT NULL, issue_categories TEXT NOT NULL,
 human_review_required INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS agent_model_calls (
 call_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES agent_sessions(session_id),
 agent_name TEXT NOT NULL, model_id TEXT, generation_id TEXT, input_tokens INTEGER, output_tokens INTEGER,
 cost_usd REAL, execution_status TEXT NOT NULL, duration_ms INTEGER NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS operational_events (
 event_id TEXT PRIMARY KEY, technician_id TEXT NOT NULL REFERENCES technicians(technician_id),
 event_type TEXT NOT NULL, unavailable_from TEXT NOT NULL, unavailable_until TEXT NOT NULL,
 reason TEXT NOT NULL, event_status TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(technician_id, event_type, unavailable_from, unavailable_until));
CREATE TABLE IF NOT EXISTS reschedule_plans (
 plan_id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES operational_events(event_id),
 plan_status TEXT NOT NULL, affected_job_count INTEGER NOT NULL, resolved_job_count INTEGER NOT NULL,
 unresolved_job_count INTEGER NOT NULL, created_at TEXT NOT NULL, approved_by TEXT, approved_at TEXT);
CREATE TABLE IF NOT EXISTS reschedule_actions (
 action_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL REFERENCES reschedule_plans(plan_id),
 job_id TEXT NOT NULL REFERENCES jobs(job_id), previous_technician_id TEXT NOT NULL,
 proposed_technician_id TEXT, previous_start TEXT NOT NULL, previous_end TEXT NOT NULL,
 proposed_start TEXT, proposed_end TEXT, action_type TEXT NOT NULL, reason TEXT NOT NULL,
 UNIQUE(plan_id, job_id));
CREATE TABLE IF NOT EXISTS customer_notifications (
 notification_id TEXT PRIMARY KEY, request_id TEXT REFERENCES customer_requests(request_id),
 job_id TEXT NOT NULL REFERENCES jobs(job_id), notification_type TEXT NOT NULL,
 recipient TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
 delivery_status TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS photo_assessments (
 request_id TEXT PRIMARY KEY REFERENCES customer_requests(request_id), filename TEXT NOT NULL,
 media_type TEXT NOT NULL, byte_size INTEGER NOT NULL, sha256 TEXT NOT NULL,
 summary TEXT NOT NULL, suggested_service_rule_id TEXT, urgency TEXT NOT NULL,
 safety_note TEXT NOT NULL, assessment_source TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS demo_capacity_cases (
 case_id TEXT PRIMARY KEY, work_date TEXT NOT NULL, service_rule_id TEXT NOT NULL REFERENCES service_rules(service_rule_id),
 window_start TEXT NOT NULL, window_end TEXT NOT NULL, expected_result TEXT NOT NULL,
 description TEXT NOT NULL, UNIQUE(service_rule_id, window_start, window_end));
"""


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    db_path = Path(path or settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)


@contextmanager
def transaction(path: str | Path | None = None):
    connection = connect(path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
