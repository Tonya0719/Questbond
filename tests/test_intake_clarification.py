"""Ambiguous or vague descriptions must trigger clarification, not a guessed service.

Regression guard for the intake ambiguity rule: a loose single-keyword lookup hit
(e.g. "water" -> AC-LEAK) must not be adopted as the service type. Area and time
window are always supplied, so the ONLY thing that can force a follow-up is the
unclear description.
"""
import pytest

from src.services.request_service import submit_request

CONTACT = {"name": "Resident", "email": "resident@example.com", "apartment": "Block A, unit 05-12"}
CONTEXT = "North 2030-01-15T10:00 2030-01-15T13:00"


def _submit(db, message):
    return submit_request(db, message, contact=CONTACT, scheduling_context=CONTEXT)


def _structured(db, request_id):
    return db.execute("SELECT * FROM structured_requests WHERE request_id=?", (request_id,)).fetchone()


@pytest.mark.parametrize("message", [
    "There is water on my floor",            # could be an aircon leak OR a pipe leak
    "I have a problem at home",              # no repair named at all
    "Something is broken and I need help",   # no trade named
    "My room is too hot",                    # symptom, not a fault
    "Please fix my spaceship engine",        # unsupported; must not match PL-FIXTURE
])
def test_ambiguous_description_asks_instead_of_guessing(db, message):
    response = _submit(db, message)
    assert response.workflow_status.value == "NEEDS_CLARIFICATION"
    request = _structured(db, response.request_id)
    # The service must stay unset rather than being guessed from a loose keyword.
    assert request["service_rule_id"] is None
    # Nothing was scheduled while the request is still unclear.
    assert db.execute("SELECT COUNT(*) FROM assignment_results WHERE request_id=? AND decision_status='ASSIGNED'",
                      (response.request_id,)).fetchone()[0] == 0


def test_clarification_question_is_specific_and_gives_an_example(db):
    response = _submit(db, "There is water on my floor")
    assert response.workflow_status.value == "NEEDS_CLARIFICATION"
    message = response.message.lower()
    assert "for example" in message
    # It asks about the repair itself, not about area/time which were provided.
    assert "what needs fixing" in message
    assert "area" not in message and "time window" not in message


@pytest.mark.parametrize("message,expected_rule", [
    ("The aircon is leaking", "AC-LEAK"),
    ("toilet blockage", "PL-BLOCK"),
    ("drain blockage", "PL-BLOCK"),
    ("power trip", "EL-TRIP"),
    ("socket repair", "EL-REPAIR"),
])
def test_clear_description_still_resolves_without_clarification(db, message, expected_rule):
    response = _submit(db, message)
    request = _structured(db, response.request_id)
    assert request["service_rule_id"] == expected_rule
    assert response.workflow_status.value == "RECOMMENDATION_CREATED"
