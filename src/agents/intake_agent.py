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
        if (settings.llm_backend in {"bedrock", "local", "gateway"}
                and self.llm_client is not None and not isinstance(self.llm_client, MockAgentClient)):
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
        # Only adopt a lookup match when it is a STRONG, unambiguous hit. A single loose
        # keyword match (e.g. "water" -> AC-LEAK, score 1) is treated as ambiguous so the
        # agent asks for clarification instead of guessing a service.
        if not service_rule_id and matches:
            top = matches[0]
            strong = top["score"] >= 2
            unambiguous = len(matches) == 1 or top["score"] > matches[1]["score"]
            if strong and unambiguous:
                service_rule_id = top["service_rule_id"]
        zone = extracted.get("zone") or context.get("zone")
        request = self.call_tool(session_id, "save_structured_request", request_id=request_id,
            customer_id=customer_id if context.get("found") else None, service_rule_id=service_rule_id,
            zone=zone, urgency=extracted.get("urgency", "NORMAL"),
            window_start=extracted.get("window_start"), window_end=extracted.get("window_end"))
        if request["ready_for_scheduling"]:
            message = "Request information is complete and ready for scheduling."
        else:
            message = self._clarification_message(request["missing_fields"])
        return {"message": message, "request": request}

    @staticmethod
    def _clarification_message(missing_fields) -> str:
        # Specific, example-bearing questions so the customer knows what to reply.
        questions = {
            "service_rule_id": ("what needs fixing — for example: the aircon is leaking, "
                                "a pipe is leaking, the toilet is blocked, or a socket needs repair"),
            "estimated_duration_min": ("what needs fixing — for example: the aircon is leaking, "
                                       "a pipe is leaking, the toilet is blocked, or a socket needs repair"),
            "zone": "which area you are in — East, West, North, South or Central",
            "window_start": ("a date and time window that works for you — "
                             "for example: 15 March, 10:00 AM to 1:00 PM"),
            "window_end": ("a date and time window that works for you — "
                           "for example: 15 March, 10:00 AM to 1:00 PM"),
        }
        # De-duplicate (service_rule_id/estimated_duration_min and window_start/window_end
        # collapse to one question each) while preserving order.
        parts = list(dict.fromkeys(questions.get(field, field) for field in missing_fields))
        if len(parts) == 1:
            return f"Could you tell me {parts[0]}?"
        joined = "; ".join(parts[:-1]) + "; and " + parts[-1]
        return f"To find the right technician, could you tell me {joined}?"
