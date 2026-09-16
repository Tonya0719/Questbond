from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Optional, Type

from pydantic import BaseModel, ConfigDict

from ..schemas.agent import AgentName
from . import intake_tools, scheduling_tools


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CustomerContextInput(ToolInput):
    customer_id: str


class ServiceRuleLookupInput(ToolInput):
    query: str


class SaveStructuredRequestInput(ToolInput):
    request_id: str
    customer_id: Optional[str] = None
    service_rule_id: Optional[str] = None
    zone: Optional[str] = None
    urgency: str = "NORMAL"
    window_start: Optional[str] = None
    window_end: Optional[str] = None


class RequestIdInput(ToolInput):
    request_id: str


class AssignmentIdInput(ToolInput):
    assignment_id: str


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_model: Type[BaseModel]
    handler: Callable[..., Dict[str, Any]]
    allowed_agents: frozenset[str]
    read_only: bool

    def bedrock_spec(self) -> dict:
        return {"toolSpec": {"name": self.name, "description": self.description,
                "inputSchema": {"json": self.input_model.model_json_schema()}}}


def build_registry() -> Dict[str, ToolDefinition]:
    intake = AgentName.INTAKE.value
    scheduling = AgentName.SCHEDULING.value
    definitions = [
        ToolDefinition("get_customer_context", "Get known customer scheduling context.", CustomerContextInput,
                       intake_tools.get_customer_context, frozenset({intake}), True),
        ToolDefinition("lookup_service_rules", "Find canonical service rules matching the customer request.", ServiceRuleLookupInput,
                       intake_tools.lookup_service_rules, frozenset({intake}), True),
        ToolDefinition("save_structured_request", "Validate and save extracted scheduling fields.", SaveStructuredRequestInput,
                       intake_tools.save_structured_request, frozenset({intake}), False),
        ToolDefinition("get_request_status", "Get readiness and structured request fields.", RequestIdInput,
                       intake_tools.get_request_status, frozenset({intake, scheduling}), True),
        ToolDefinition("recommend_assignment", "Run the complete deterministic assignment engine.", RequestIdInput,
                       scheduling_tools.recommend_assignment, frozenset({scheduling}), False),
        ToolDefinition("validate_assignment_recommendation", "Independently validate assignment invariants.", AssignmentIdInput,
                       scheduling_tools.validate_assignment_recommendation, frozenset({scheduling}), True),
        ToolDefinition("get_assignment_decision_trace", "Get selected and excluded candidate evidence.", AssignmentIdInput,
                       scheduling_tools.get_assignment_decision_trace, frozenset({scheduling}), True),
    ]
    return {definition.name: definition for definition in definitions}


def specs_for_agent(registry: Dict[str, ToolDefinition], agent_name: str) -> list[dict]:
    return [item.bedrock_spec() for item in registry.values() if agent_name in item.allowed_agents]
