from __future__ import annotations
import json

from ..config import settings
from ..llm.bedrock_client import run_tool_loop
from ..llm.mock_client import MockAgentClient
from ..schemas.agent import AgentName
from .base_agent import BaseAgent
from .prompts import SCHEDULING_PROMPT
from ..services.decision_service import explain_decision


class SchedulingOperationsAgent(BaseAgent):
    agent_name = AgentName.SCHEDULING.value
    system_prompt = SCHEDULING_PROMPT

    def run(self, session_id: str, request_id: str) -> dict:
        status = self.call_tool(session_id, "get_request_status", request_id=request_id)
        if not status.get("ready_for_scheduling"):
            return {"status": "NEEDS_CLARIFICATION", "request_id": request_id,
                    "missing_fields": status.get("missing_fields", [])}
        if (settings.llm_backend in {"bedrock", "local", "gateway"}
                and self.llm_client is not None and not isinstance(self.llm_client, MockAgentClient)):
            prompt = f"Process ready request {request_id}. Use tools; do not select a technician yourself."
            text, _ = run_tool_loop(self.llm_client, self.executor, session_id, self.agent_name,
                                    [{"role": "user", "content": [{"text": prompt}]}],
                                    self.system_prompt, self.tool_specs)
            latest = self.executor.connection.execute("""SELECT output_json FROM agent_tool_calls
                WHERE session_id=? AND tool_name='recommend_assignment' AND execution_status='SUCCESS'
                ORDER BY created_at DESC LIMIT 1""", (session_id,)).fetchone()
            if not latest:
                raise RuntimeError("Scheduling agent completed without creating an assignment result")
            assignment_id = json.loads(latest["output_json"])["assignment_id"]
            validation = self.call_tool(session_id, "validate_assignment_recommendation", assignment_id=assignment_id)
            trace = self.call_tool(session_id, "get_assignment_decision_trace", assignment_id=assignment_id)
            row = self.executor.connection.execute(
                "SELECT * FROM assignment_results WHERE assignment_id=?", (assignment_id,)).fetchone()
            assignment = dict(row)
            assignment["recommendation_reason"] = json.loads(assignment["recommendation_reason"])
            return {"message": explain_decision(self.executor.connection, assignment, validation, trace),
                    "model_explanation": text, "assignment": assignment, "validation": validation, "decision_trace": trace}
        assignment = self.call_tool(session_id, "recommend_assignment", request_id=request_id)
        validation = self.call_tool(session_id, "validate_assignment_recommendation",
                                    assignment_id=assignment["assignment_id"])
        trace = self.call_tool(session_id, "get_assignment_decision_trace",
                               assignment_id=assignment["assignment_id"])
        return {"message": explain_decision(self.executor.connection, assignment, validation, trace), "assignment": assignment,
                "validation": validation, "decision_trace": trace}

    @staticmethod
    def _explain(assignment: dict, validation: dict) -> str:
        status = assignment["decision_status"]
        if status == "ASSIGNED" and validation["valid"]:
            return (f"Recommended {assignment['technician_id']} from {assignment['scheduled_start']} "
                    f"to {assignment['scheduled_end']}. The deterministic recommendation passed validation.")
        if status == "NEEDS_CLARIFICATION":
            return "The request needs more information before scheduling."
        if status == "NO_FEASIBLE_TECHNICIAN":
            return "No feasible technician was found; human review is required."
        return "The recommendation failed validation and requires human review."
