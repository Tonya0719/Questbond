"""Customer-facing clarification text must stay specific even when the structured
request row is missing, NULL, or partially populated.

Regression guard for the bug where `customer_response()` fell back to the generic
"Could you tell us the missing details for your visit?" whenever the gateway path
left `structured_requests` empty or with a NULL `missing_fields` cell.
"""
import json

import pytest

from src.services.customer_response import customer_response

GENERIC_FALLBACK = 'Could you tell us the missing details for your visit?'


def _seed_request(db, request_id):
    """Insert the minimal customer_requests row so FKs are satisfied."""
    db.execute(
        "INSERT INTO customer_requests VALUES (?,?,?,?,?,?)",
        (request_id, 'NEW', '2030-01-15T09:00', 'chat', 'There is water on my floor', 'en'),
    )


def _seed_session(db, session_id, request_id, status='NEEDS_CLARIFICATION'):
    db.execute(
        "INSERT INTO agent_sessions VALUES (?,?,?,?,?,?,?)",
        (session_id, request_id, None, 'intake', status, '2030-01-15T09:00', '2030-01-15T09:00'),
    )


def _seed_structured(db, request_id, missing_fields, service_rule_id=None):
    db.execute(
        "INSERT INTO structured_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (request_id, None, service_rule_id, None, None, None, 'NORMAL', None, None, None,
         missing_fields, 0),
    )


def _respond(db, request_id, missing_fields=..., service_rule_id=None):
    """Build a NEEDS_CLARIFICATION session and return the customer text.

    Pass missing_fields=... (default) to skip inserting a structured_requests row.
    Pass missing_fields=None to insert a row with a NULL missing_fields cell.
    """
    session_id = f'SES-{request_id}'
    _seed_request(db, request_id)
    _seed_session(db, session_id, request_id)
    if missing_fields is not ...:
        _seed_structured(db, request_id, missing_fields, service_rule_id=service_rule_id)
    db.commit()
    return customer_response(db, session_id)


def test_no_structured_row_asks_for_service_type_with_example(db):
    text = _respond(db, 'REQ-NOROW')
    lowered = text.lower()
    assert 'what needs fixing' in lowered
    assert 'for example' in lowered
    assert text != GENERIC_FALLBACK


def test_null_missing_fields_is_robust_and_asks_service_type(db):
    # A NULL-ish missing_fields cell (stored as the JSON literal "null", which
    # json.loads turns into None rather than a list) must not raise and must fall
    # back to asking for the service type.
    text = _respond(db, 'REQ-NULL', missing_fields='null')
    lowered = text.lower()
    assert 'what needs fixing' in lowered
    assert 'for example' in lowered
    assert text != GENERIC_FALLBACK


def test_service_rule_and_duration_missing_asks_service_type_with_example(db):
    text = _respond(db, 'REQ-SVC',
                    missing_fields=json.dumps(['service_rule_id', 'estimated_duration_min']))
    lowered = text.lower()
    assert 'what needs fixing' in lowered
    assert 'for example' in lowered
    # Nothing else is missing, so no area/time question.
    assert 'area' not in lowered
    assert 'date and time' not in lowered


def test_only_window_missing_asks_time_not_service_type(db):
    text = _respond(db, 'REQ-WIN',
                    missing_fields=json.dumps(['window_start', 'window_end']),
                    service_rule_id=None)
    lowered = text.lower()
    # Service type is known (not in missing), so it must NOT ask what needs fixing.
    assert 'what needs fixing' not in lowered
    assert 'date and time' in lowered
    assert 'for example' in lowered


def test_multiple_missing_fields_merge_into_one_message_each_with_example(db):
    text = _respond(db, 'REQ-MULTI',
                    missing_fields=json.dumps(['service_rule_id', 'zone', 'window_start', 'window_end']))
    lowered = text.lower()
    assert 'what needs fixing' in lowered
    assert 'area' in lowered
    assert 'date and time' in lowered
    # Merged into a single sentence using ';' and 'and'.
    assert ';' in text
    assert ' and ' in text
    assert text.count('for example') == 2  # service-type + time examples
