from __future__ import annotations
import json

from ..config import settings
from ..llm.bedrock_client import run_tool_loop
from ..llm.mock_client import MockAgentClient
from ..schemas.agent import AgentName
from .base_agent import BaseAgent
from .prompts import DISRUPTION_RECOVERY_PROMPT, SCHEDULING_PROMPT
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

    def run_disruption_recovery(self, session_id: str, event_id: str) -> dict:
        """Coordinate a deterministic recovery proposal for a technician disruption.

        The agent reads context, asks the deterministic engine to propose a recovery,
        and reads the plan back for explanation. It never selects a technician/time and
        never approves, rejects or applies the plan (those stay human-owned).
        """
        if (settings.llm_backend in {"bedrock", "local", "gateway"}
                and self.llm_client is not None and not isinstance(self.llm_client, MockAgentClient)):
            prompt = (f"A technician disruption occurred (event {event_id}). Use your tools to read the "
                      f"context, propose a deterministic recovery, and explain the plan. Do not choose "
                      f"replacements yourself and do not approve, reject or apply anything.")
            text, _ = run_tool_loop(self.llm_client, self.executor, session_id, self.agent_name,
                                    [{"role": "user", "content": [{"text": prompt}]}],
                                    DISRUPTION_RECOVERY_PROMPT, self.tool_specs)
            plan = self.call_tool(session_id, "get_recovery_plan", event_id=event_id)
            return {"message": self._explain_recovery(plan), "model_explanation": text,
                    "event_id": event_id, "plan": plan}
        context = self.call_tool(session_id, "get_disruption_context", event_id=event_id)
        self.call_tool(session_id, "propose_recovery", event_id=event_id)
        plan = self.call_tool(session_id, "get_recovery_plan", event_id=event_id)
        return {"message": self._explain_recovery(plan), "event_id": event_id,
                "context": context, "plan": plan}

    @staticmethod
    def _explain_recovery(plan: dict) -> str:
        summary = plan["plan"]
        affected = summary["affected_job_count"]
        resolved = summary["resolved_job_count"]
        unresolved = summary["unresolved_job_count"]
        if unresolved:
            return (f"Recovery proposed for {affected} affected job(s): {resolved} resolved, "
                    f"{unresolved} unresolved. The plan has unresolved jobs and requires human review; "
                    f"it cannot be partially applied.")
        if summary.get("requires_human_approval"):
            return (f"Recovery proposed for {affected} affected job(s), all resolved. "
                    f"Changes affect confirmed appointments and require coordinator approval.")
        return (f"Recovery proposed for {affected} affected job(s), all resolved. "
                f"No confirmed appointment changes require approval.")

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
