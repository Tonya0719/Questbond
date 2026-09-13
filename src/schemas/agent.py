from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AgentName(str, Enum):
    INTAKE = "customer_intake_agent"
    SCHEDULING = "scheduling_operations_agent"


class WorkflowStatus(str, Enum):
    COLLECTING_INFORMATION = "COLLECTING_INFORMATION"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    READY_FOR_SCHEDULING = "READY_FOR_SCHEDULING"
    ASSIGNMENT_IN_PROGRESS = "ASSIGNMENT_IN_PROGRESS"
    RECOMMENDATION_CREATED = "RECOMMENDATION_CREATED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    NO_FEASIBLE_ASSIGNMENT = "NO_FEASIBLE_ASSIGNMENT"
    ERROR = "ERROR"


class AgentResponse(BaseModel):
    session_id: str
    request_id: str
    workflow_status: WorkflowStatus
    message: str
    handoffs: List[Dict[str, Any]] = Field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
