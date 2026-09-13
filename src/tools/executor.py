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
            output = definition.handler(self.connection, **validated.model_dump())
            return output
        except (ValidationError, ValueError, ToolExecutionError) as exc:
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
