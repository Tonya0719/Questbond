"""The customer must see the clean, tool-authored clarification question the Intake
Agent produces via ask_customer_clarification, never the LLM's free-text reasoning.
Recommendation results keep the sanitised projection that never leaks technician
identity or internal reasoning.
"""
from uuid import uuid4

from src.orchestration.orchestrator import AgentOrchestrator
from src.schemas.agent import AgentName, WorkflowStatus


# The clean, customer-facing question produced by ask_customer_clarification.
CLEAN_QUESTION = ("Is the water coming from the aircon or a pipe? "
                  "For example: the aircon is dripping, or a pipe under the sink is leaking.")


def _seed_session(db, status=WorkflowStatus.NEEDS_CLARIFICATION.value, request_id='REQ-CLARIFY'):
    session_id = f'SES-{uuid4().hex[:12]}'
    db.execute(
        "INSERT INTO customer_requests VALUES (?,?,?,?,?,?)",
        (request_id, 'NEW', '2030-01-15T09:00', 'chat', 'There is water on my floor', 'en'),
    )
    db.execute(
        "INSERT INTO agent_sessions VALUES (?,?,?,?,?,?,?)",
        (session_id, request_id, None, AgentName.INTAKE.value, status,
         '2030-01-15T09:00', '2030-01-15T09:00'),
    )
    db.commit()
    return session_id


def _customer_text_for(db, session_id):
    return db.execute(
        '''SELECT cm.content FROM customer_messages cm
           JOIN agent_messages m ON m.message_id=cm.message_id
           WHERE m.session_id=? ORDER BY m.rowid DESC LIMIT 1''', (session_id,)).fetchone()[0]


def test_clarification_assistant_message_shows_clean_tool_question(db):
    """The customer sees the clean tool-authored question, not the LLM's free text."""
    orchestrator = AgentOrchestrator(db)
    session_id = _seed_session(db)
    internal_free_text = ("The lookup returned multiple matches: AC-LEAK and PL-LEAK. "
                          "I cannot set a service_rule_id yet. " + CLEAN_QUESTION)
    # The orchestrator passes the clean tool question as public_content, never the
    # free-text reasoning.
    orchestrator._record_message(session_id, 'assistant', internal_free_text,
                                 public_content=CLEAN_QUESTION)
    public = _customer_text_for(db, session_id)
    assert public == CLEAN_QUESTION
    assert not any(term in public for term in
                   ('lookup returned', 'service_rule_id', 'cannot set', 'AC-LEAK', 'PL-LEAK'))


def test_recommendation_message_stays_sanitised_not_llm_original(db):
    """Without public_content, assistant text falls back to the safe projection."""
    orchestrator = AgentOrchestrator(db)
    session_id = _seed_session(db, status=WorkflowStatus.NO_FEASIBLE_ASSIGNMENT.value)
    internal = ("We propose technician Blair (workload tiebreak, certification match) "
                "for 2030-01-15T14:00.")
    orchestrator._record_message(session_id, 'assistant', internal)
    public = _customer_text_for(db, session_id)
    assert public == 'No technician is free in that window. Could you choose another date or time?'
    assert not any(term in public for term in
                   ('Blair', 'workload', 'tiebreak', 'certification', 'T14:00'))


def test_internal_leak_marker_falls_back_to_sanitised(db):
    """If public_content carries an internal marker, we refuse the raw text."""
    orchestrator = AgentOrchestrator(db)
    session_id = _seed_session(db)
    leaky = "Customer-provided booking details: East 2030-01-15T14:00. Is it a pipe or aircon?"
    orchestrator._record_message(session_id, 'assistant', leaky, public_content=leaky)
    public = _customer_text_for(db, session_id)
    assert 'Customer-provided booking details' not in public
    # Falls back to the NEEDS_CLARIFICATION projection.
    assert 'what needs fixing' in public.lower()


ORCHESTRATOR_QUESTION = ("Which service do you need? For example: the aircon is leaking, "
                         "or a pipe is leaking.")

# The kind of internal reasoning that must never reach the customer.
INTERNAL_FREE_TEXT = ("The lookup returned multiple matches: AC-LEAK... I cannot set a "
                      "service_rule_id yet. " + ORCHESTRATOR_QUESTION)


def _seed_incomplete_structured(db, request_id):
    """A NEEDS_CLARIFICATION structured request with the service type still missing."""
    import json
    db.execute(
        "INSERT INTO structured_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (request_id, None, None, None, None, None, 'NORMAL', None, None, None,
         json.dumps(['service_rule_id']), 0),
    )
    db.commit()


def test_orchestrator_clarification_shows_clean_question_not_reasoning(db):
    """The intake clarification branch stores the tool question, not the LLM free text."""
    request_id = 'REQ-CLEAN'
    orchestrator = AgentOrchestrator(db)
    session_id = _seed_session(db, request_id=request_id,
                               status=WorkflowStatus.COLLECTING_INFORMATION.value)
    _seed_incomplete_structured(db, request_id)

    def fake_run(self, sess, req, cust, raw):
        return {"message": INTERNAL_FREE_TEXT,
                "request": {"ready_for_scheduling": False, "missing_fields": ["service_rule_id"]},
                "clarification_question": ORCHESTRATOR_QUESTION}

    orchestrator.intake_agent.run = fake_run.__get__(orchestrator.intake_agent)
    response = orchestrator._process_intake(session_id, request_id, None, "There is water on my floor")
    assert response.workflow_status == WorkflowStatus.NEEDS_CLARIFICATION
    public = _customer_text_for(db, session_id)
    assert public == ORCHESTRATOR_QUESTION
    assert not any(term in public for term in ('lookup returned', 'service_rule_id', 'cannot set'))


def test_orchestrator_clarification_falls_back_to_template_when_no_question(db):
    """When the LLM asked no clean question, the customer sees the safe template."""
    request_id = 'REQ-FALLBACK'
    orchestrator = AgentOrchestrator(db)
    session_id = _seed_session(db, request_id=request_id,
                               status=WorkflowStatus.COLLECTING_INFORMATION.value)
    _seed_incomplete_structured(db, request_id)

    def fake_run(self, sess, req, cust, raw):
        return {"message": INTERNAL_FREE_TEXT,
                "request": {"ready_for_scheduling": False, "missing_fields": ["service_rule_id"]},
                "clarification_question": None}

    orchestrator.intake_agent.run = fake_run.__get__(orchestrator.intake_agent)
    response = orchestrator._process_intake(session_id, request_id, None, "There is water on my floor")
    assert response.workflow_status == WorkflowStatus.NEEDS_CLARIFICATION
    public = _customer_text_for(db, session_id).lower()
    assert 'what needs fixing' in public
    assert 'for example' in public
    assert not any(term in public for term in ('lookup returned', 'service_rule_id', 'cannot set'))
