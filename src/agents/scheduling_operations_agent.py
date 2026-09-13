from __future__ import annotations

from ..config import settings
from ..llm.bedrock_client import run_tool_loop
from ..schemas.agent import AgentName
from .base_agent import BaseAgent


class SchedulingOperationsAgent(BaseAgent):
    agent_name = AgentName.SCHEDULING.value
    system_prompt = """You are the Scheduling Operations Agent. Never choose, replace, or rerank a
technician yourself. Use recommend_assignment for every decision, validate the returned recommendation,
and ground explanations only in the decision trace. Return incomplete requests to intake and route
no-feasible or invalid outcomes to human review. Never modify the current schedule."""

    def run(self, session_id: str, request_id: str) -> dict:
        status = self.call_tool(session_id, "get_request_status", request_id=request_id)
        if not status.get("ready_for_scheduling"):
            return {"status": "NEEDS_CLARIFICATION", "request_id": request_id,
                    "missing_fields": status.get("missing_fields", [])}
        if settings.llm_backend in {"bedrock", "local"} and self.llm_client is not None:
            prompt = f"Process ready request {request_id}. Use tools; do not select a technician yourself."
            text, _ = run_tool_loop(self.llm_client, self.executor, session_id, self.agent_name,
                                    [{"role": "user", "content": [{"text": prompt}]}],
                                    self.system_prompt, self.tool_specs)
            latest = self.executor.connection.execute(
                "SELECT assignment_id FROM assignment_results WHERE request_id=? ORDER BY created_at DESC LIMIT 1",
                (request_id,)).fetchone()
            if not latest:
                raise RuntimeError("Scheduling agent completed without creating an assignment result")
            assignment_id = latest["assignment_id"]
            validation = self.call_tool(session_id, "validate_assignment_recommendation", assignment_id=assignment_id)
            trace = self.call_tool(session_id, "get_assignment_decision_trace", assignment_id=assignment_id)
            return {"message": text, "assignment": trace, "validation": validation}
        assignment = self.call_tool(session_id, "recommend_assignment", request_id=request_id)
        validation = self.call_tool(session_id, "validate_assignment_recommendation",
                                    assignment_id=assignment["assignment_id"])
        trace = self.call_tool(session_id, "get_assignment_decision_trace",
                               assignment_id=assignment["assignment_id"])
        return {"message": self._explain(assignment, validation), "assignment": assignment,
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
