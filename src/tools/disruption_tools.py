"""Event-scoped disruption tools for the Scheduling Operations Agent.

These tools expose read + deterministic-proposal capabilities only. They never
approve, reject or mutate schedules; those remain human-owned services outside
the LLM tool surface. Every tool is scoped by ``event_id`` and the ToolExecutor
verifies the event belongs to the calling session (see disruption_sessions).
"""
from __future__ import annotations

from ..services.disruption_service import (
    create_recovery_plan,
    get_plan as _get_plan_by_id,
)


def _event(connection, event_id: str):
    event = connection.execute("SELECT * FROM operational_events WHERE event_id=?", (event_id,)).fetchone()
    if not event:
        raise ValueError(f"Unknown event_id: {event_id}")
    return event


def _latest_plan_id(connection, event_id: str):
    row = connection.execute(
        "SELECT plan_id FROM reschedule_plans WHERE event_id=? ORDER BY created_at DESC LIMIT 1",
        (event_id,)).fetchone()
    return row['plan_id'] if row else None


def get_disruption_context(connection, event_id: str) -> dict:
    """Return the disruption event plus a read-only summary of affected confirmed jobs."""
    event = _event(connection, event_id)
    affected = connection.execute(
        """SELECT s.job_id, s.technician_id, s.scheduled_start, s.scheduled_end,
                  j.priority, j.zone, sr.subtype
           FROM schedules s JOIN jobs j ON j.job_id=s.job_id
           JOIN service_rules sr ON sr.service_rule_id=j.service_rule_id
           WHERE s.technician_id=? AND s.assignment_status IN ('ASSIGNED','CONFIRMED')
             AND j.status IN ('SCHEDULED','IN_PROGRESS')
             AND s.scheduled_start < ? AND s.scheduled_end > ?
           ORDER BY CASE j.priority WHEN 'HIGH' THEN 0 ELSE 1 END, s.scheduled_start, s.job_id""",
        (event['technician_id'], event['unavailable_until'], event['unavailable_from'])).fetchall()
    return {
        'event_id': event['event_id'],
        'technician_id': event['technician_id'],
        'event_type': event['event_type'],
        'unavailable_from': event['unavailable_from'],
        'unavailable_until': event['unavailable_until'],
        'reason': event['reason'],
        'event_status': event['event_status'],
        'affected_jobs': [dict(row) for row in affected],
        'affected_job_count': len(affected),
    }


def propose_recovery(connection, event_id: str) -> dict:
    """Run the deterministic recovery engine for the event and return the proposal.

    Idempotent: reuses the existing plan for the same event/interval. Never
    mutates ``schedules`` (proposal only).
    """
    event = _event(connection, event_id)
    return create_recovery_plan(connection, event['technician_id'], event['unavailable_from'],
                                event['unavailable_until'], event_type=event['event_type'],
                                reason=event['reason'])


def get_recovery_plan(connection, event_id: str) -> dict:
    """Return the current recovery plan and its governance decision evidence."""
    plan_id = _latest_plan_id(connection, event_id)
    if not plan_id:
        raise ValueError(f"No recovery plan exists for event_id: {event_id}")
    return _get_plan_by_id(connection, plan_id)
