from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from ..agents import CustomerIntakeAgent, SchedulingOperationsAgent
from ..config import settings
from ..llm import BedrockConverseClient, LocalOpenAICompatibleClient, MockAgentClient
from ..schemas.agent import AgentName, AgentResponse, WorkflowStatus
from ..schemas.handoff import AgentHandoff
from ..tools import ToolExecutor, build_registry
from .handoff import persist_handoff
from .state_machine import ensure_transition
from ..services.triage_service import get_triage


class AgentOrchestrator:
    def __init__(self, connection, llm_client=None):
        self.connection = connection
        self.registry = build_registry()
        self.executor = ToolExecutor(connection, self.registry)
        if llm_client is None:
            clients = {"mock": MockAgentClient, "local": LocalOpenAICompatibleClient,
                       "bedrock": BedrockConverseClient}
            try:
                llm_client = clients[settings.llm_backend]()
            except KeyError as exc:
                raise ValueError(f"Unsupported LLM_BACKEND: {settings.llm_backend}") from exc
        self.intake_agent = CustomerIntakeAgent(self.executor, self.registry, llm_client)
        self.scheduling_agent = SchedulingOperationsAgent(self.executor, self.registry, llm_client)

    def run_request(self, request_id: str, customer_id: str, raw_message: str) -> AgentResponse:
        session_id = f"SES-{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        self.connection.execute("INSERT INTO agent_sessions VALUES (?,?,?,?,?,?,?)",
            (session_id, request_id, customer_id, AgentName.INTAKE.value,
             WorkflowStatus.COLLECTING_INFORMATION.value, now, now))
        self._record_message(session_id, "user", raw_message)
        self.connection.commit()
        return self._process_intake(session_id, request_id, customer_id, raw_message)

    def continue_session(self, session_id: str, message: str) -> AgentResponse:
        session = self.connection.execute("SELECT * FROM agent_sessions WHERE session_id=?", (session_id,)).fetchone()
        if not session:
            raise ValueError(f"Unknown session_id: {session_id}")
        if session["workflow_status"] != WorkflowStatus.NEEDS_CLARIFICATION.value:
            raise ValueError("Only sessions awaiting clarification can receive a customer reply")
        self._transition(session_id, WorkflowStatus.COLLECTING_INFORMATION, AgentName.INTAKE.value)
        self._record_message(session_id, "user", message)
        raw = self.connection.execute("SELECT raw_message FROM customer_requests WHERE request_id=?",
                                      (session["request_id"],)).fetchone()[0]
        replies = [row[0] for row in self.connection.execute(
            "SELECT content FROM agent_messages WHERE session_id=? AND role='user' ORDER BY created_at",
            (session_id,)).fetchall()]
        combined = " ".join(replies or [raw])
        return self._process_intake(session_id, session["request_id"], session["customer_id"], combined)

    def _process_intake(self, session_id: str, request_id: str, customer_id: str,
                        raw_message: str) -> AgentResponse:
        try:
            intake = self.intake_agent.run(session_id, request_id, customer_id, raw_message)
            request = intake["request"]
            triage = get_triage(self.connection, request_id)
            if triage["human_review_required"]:
                reason = ("Possible safety hazard: " + ", ".join(triage["hazard_flags"]) if triage["hazard_flags"]
                          else "Multiple service issues were reported; the coordinator must separate and review them.")
                message = reason + " No technician has been booked."
                self._transition(session_id, WorkflowStatus.HUMAN_REVIEW_REQUIRED, AgentName.INTAKE.value)
                handoff = self._handoff(session_id, AgentName.INTAKE.value, "human_coordinator",
                                        "HUMAN_REVIEW_REQUIRED", request_id, payload={"message": message}, evidence=triage)
                self._record_message(session_id, "assistant", message)
                return AgentResponse(session_id=session_id, request_id=request_id,
                    workflow_status=WorkflowStatus.HUMAN_REVIEW_REQUIRED, message=message, handoffs=[handoff])
            if not request.get("ready_for_scheduling"):
                self._transition(session_id, WorkflowStatus.NEEDS_CLARIFICATION, AgentName.INTAKE.value)
                handoff = self._handoff(session_id, AgentName.INTAKE.value, "customer",
                    "CUSTOMER_CLARIFICATION_REQUIRED", request_id, payload={
                        "missing_fields": request.get("missing_fields", []), "message": intake["message"]})
                self._record_message(session_id, "assistant", intake["message"])
                return AgentResponse(session_id=session_id, request_id=request_id,
                    workflow_status=WorkflowStatus.NEEDS_CLARIFICATION, message=intake["message"], handoffs=[handoff])

            self._transition(session_id, WorkflowStatus.READY_FOR_SCHEDULING, AgentName.INTAKE.value)
            ready_handoff = self._handoff(session_id, AgentName.INTAKE.value, AgentName.SCHEDULING.value,
                                           "REQUEST_READY", request_id, payload={"structured_request": request})
            self._transition(session_id, WorkflowStatus.ASSIGNMENT_IN_PROGRESS, AgentName.SCHEDULING.value)
            scheduling = self.scheduling_agent.run(session_id, request_id)
            assignment = scheduling.get("assignment", {})
            decision = assignment.get("decision_status") or assignment.get("status")
            valid = scheduling.get("validation", {}).get("valid", True)
            if decision == "ASSIGNED" and valid:
                final_status = WorkflowStatus.RECOMMENDATION_CREATED
                handoff_type = "ASSIGNMENT_RECOMMENDED"
            elif decision == "NEEDS_CLARIFICATION":
                final_status = WorkflowStatus.NEEDS_CLARIFICATION
                handoff_type = "REQUEST_CLARIFICATION_REQUIRED"
            elif decision == "NO_FEASIBLE_TECHNICIAN":
                final_status = WorkflowStatus.NO_FEASIBLE_ASSIGNMENT
                handoff_type = "HUMAN_REVIEW_REQUIRED"
            else:
                final_status = WorkflowStatus.HUMAN_REVIEW_REQUIRED
                handoff_type = "HUMAN_REVIEW_REQUIRED"
            self._transition(session_id, final_status, AgentName.SCHEDULING.value)
            final_handoff = self._handoff(session_id, AgentName.SCHEDULING.value, "human_coordinator",
                handoff_type, request_id, assignment_id=assignment.get("assignment_id"),
                payload={"message": scheduling["message"], "assignment": assignment},
                evidence=scheduling.get("decision_trace", scheduling.get("validation", {})))
            self._record_message(session_id, "assistant", scheduling["message"])
            return AgentResponse(session_id=session_id, request_id=request_id, workflow_status=final_status,
                message=scheduling["message"], handoffs=[ready_handoff, final_handoff], result=scheduling)
        except Exception as error:
            self.connection.execute("UPDATE agent_sessions SET workflow_status=?, updated_at=? WHERE session_id=?",
                (WorkflowStatus.ERROR.value, datetime.now(timezone.utc).isoformat(), session_id))
            self.connection.commit()
            self._record_message(session_id, "assistant", f"Processing failed: {error}. Coordinator review is required.")
            raise

    def _record_message(self, session_id: str, role: str, content: str):
        self.connection.execute("INSERT INTO agent_messages VALUES (?,?,?,?,?)",
            (f"MSG-{uuid4().hex[:12]}", session_id, role, content, datetime.now(timezone.utc).isoformat()))
        self.connection.commit()

    def _transition(self, session_id: str, target: WorkflowStatus, current_agent: str):
        current = self.connection.execute("SELECT workflow_status FROM agent_sessions WHERE session_id=?", (session_id,)).fetchone()
        ensure_transition(current["workflow_status"], target.value)
        self.connection.execute("UPDATE agent_sessions SET workflow_status=?, current_agent=?, updated_at=? WHERE session_id=?",
            (target.value, current_agent, datetime.now(timezone.utc).isoformat(), session_id))
        self.connection.commit()

    def _handoff(self, session_id, source, target, handoff_type, request_id,
                 assignment_id=None, payload=None, evidence=None):
        handoff = AgentHandoff(handoff_id=f"HO-{uuid4().hex[:12]}", session_id=session_id,
            source_agent=source, target_agent=target, handoff_type=handoff_type, request_id=request_id,
            assignment_id=assignment_id, payload=payload or {}, evidence=evidence or {})
        return persist_handoff(self.connection, handoff)
