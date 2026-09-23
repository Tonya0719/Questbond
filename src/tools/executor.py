from __future__ import annotations

import json
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Dict
from uuid import uuid4

from pydantic import ValidationError


class ToolExecutionError(RuntimeError):
    pass


class ToolExecutor:
    def __init__(self, connection, registry):
        self.connection = connection
        self.registry = registry

    def execute(self, session_id: str, agent_name: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        started = perf_counter()
        status, output = "SUCCESS", {}
        try:
            definition = self.registry.get(tool_name)
            if definition is None:
                raise ToolExecutionError(f"Unknown tool: {tool_name}")
            if agent_name not in definition.allowed_agents:
                raise ToolExecutionError(f"Agent {agent_name} is not allowed to call {tool_name}")
            validated = definition.input_model.model_validate(arguments)
            session = self.connection.execute("SELECT * FROM agent_sessions WHERE session_id=?", (session_id,)).fetchone()
            if not session or session["current_agent"] != agent_name:
                raise ToolExecutionError("The tool call is not owned by the active session agent")
            scoped = validated.model_dump()
            if "request_id" in scoped and scoped["request_id"] != session["request_id"]:
                raise ToolExecutionError("The tool cannot access a different request")
            if scoped.get("customer_id") and scoped["customer_id"] != session["customer_id"]:
                raise ToolExecutionError("The tool cannot access a different customer")
            if "assignment_id" in scoped:
                assignment = self.connection.execute("SELECT request_id FROM assignment_results WHERE assignment_id=?",
                                                     (scoped["assignment_id"],)).fetchone()
                if not assignment or assignment["request_id"] != session["request_id"]:
                    raise ToolExecutionError("The tool cannot access a different request's assignment")
            # Disruption tools are event-scoped. This is an additional, orthogonal check that
            # does not weaken the request/customer/assignment ownership checks above: the event
            # must be mapped to the current session via disruption_sessions.
            if "event_id" in scoped:
                mapping = self.connection.execute(
                    "SELECT 1 FROM disruption_sessions WHERE session_id=? AND event_id=?",
                    (session_id, scoped["event_id"])).fetchone()
                if not mapping:
                    raise ToolExecutionError("The tool cannot access an event outside its session")
            cached = None
            if tool_name == "recommend_assignment":
                cached = self.connection.execute("""SELECT output_json FROM agent_tool_calls
                    WHERE session_id=? AND tool_name='recommend_assignment' AND execution_status='SUCCESS'
                    ORDER BY created_at DESC LIMIT 1""", (session_id,)).fetchone()
            output = json.loads(cached["output_json"]) if cached else definition.handler(self.connection, **validated.model_dump())
            return output
        except Exception as exc:
            status = "ERROR"
            output = {"error": str(exc)}
            raise ToolExecutionError(str(exc)) from exc
        finally:
            duration = max(0, int((perf_counter() - started) * 1000))
            self.connection.execute(
                "INSERT INTO agent_tool_calls VALUES (?,?,?,?,?,?,?,?,?)",
                (f"TC-{uuid4().hex[:12]}", session_id, agent_name, tool_name,
                 json.dumps(arguments, sort_keys=True, default=str),
                 json.dumps(output, sort_keys=True, default=str), status, duration,
                 datetime.now(timezone.utc).isoformat()),
            )
            self.connection.commit()
