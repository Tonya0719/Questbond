import json

from ..schemas.handoff import AgentHandoff


def persist_handoff(connection, handoff: AgentHandoff) -> dict:
    connection.execute("INSERT INTO agent_handoffs VALUES (?,?,?,?,?,?,?,?,?,?)",
        (handoff.handoff_id, handoff.session_id, handoff.source_agent, handoff.target_agent,
         handoff.handoff_type, handoff.request_id, handoff.assignment_id,
         json.dumps(handoff.payload, sort_keys=True), json.dumps(handoff.evidence, sort_keys=True),
         handoff.created_at))
    connection.commit()
    return handoff.model_dump()
