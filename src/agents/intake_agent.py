from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo

from ..config import settings
from ..llm.bedrock_client import run_tool_loop
from ..llm.mock_client import MockAgentClient
from ..schemas.agent import AgentName
from .base_agent import BaseAgent
from .prompts import INTAKE_PROMPT


class CustomerIntakeAgent(BaseAgent):
    agent_name = AgentName.INTAKE.value
    system_prompt = INTAKE_PROMPT

    def run(self, session_id: str, request_id: str, customer_id: str, raw_message: str) -> dict:
        if settings.llm_backend in {"bedrock", "local", "gateway"} and self.llm_client is not None:
            today = datetime.now(ZoneInfo("Asia/Singapore")).date().isoformat()
            prompt = (f"Today is {today}; timezone is Asia/Singapore. Use local ISO datetimes without timezone offsets. "
                      f"request_id={request_id}; customer_id={customer_id}; customer message={raw_message}. "
                      "Use tools to build the request and finish with either READY or a clarification question.")
            text, _ = run_tool_loop(self.llm_client, self.executor, session_id, self.agent_name,
                                    [{"role": "user", "content": [{"text": prompt}]}],
                                    self.system_prompt, self.tool_specs)
            status = self.call_tool(session_id, "get_request_status", request_id=request_id)
            return {"message": text, "request": status}
        return self._run_mock(session_id, request_id, customer_id, raw_message)

    def _run_mock(self, session_id: str, request_id: str, customer_id: str, raw_message: str) -> dict:
        client = self.llm_client if isinstance(self.llm_client, MockAgentClient) else MockAgentClient()
        context = self.call_tool(session_id, "get_customer_context", customer_id=customer_id)
        matches = self.call_tool(session_id, "lookup_service_rules", query=raw_message)["matches"]
        extracted = client.extract_request(raw_message)
        service_rule_id = extracted.get("service_rule_id")
        if not service_rule_id and len(matches) == 1:
            service_rule_id = matches[0]["service_rule_id"]
        zone = extracted.get("zone") or context.get("zone")
        request = self.call_tool(session_id, "save_structured_request", request_id=request_id,
            customer_id=customer_id if context.get("found") else None, service_rule_id=service_rule_id,
            zone=zone, urgency=extracted.get("urgency", "NORMAL"),
            window_start=extracted.get("window_start"), window_end=extracted.get("window_end"))
        if request["ready_for_scheduling"]:
            message = "Request information is complete and ready for scheduling."
        else:
            labels = {"service_rule_id": "the type of repair", "zone": "your area",
                      "window_start": "your available start time", "window_end": "your available end time",
                      "estimated_duration_min": "a supported service type"}
            message = "Could you provide " + ", ".join(dict.fromkeys(labels.get(field, field) for field in request["missing_fields"])) + "?"
        return {"message": message, "request": request}
