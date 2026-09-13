from __future__ import annotations

from typing import Dict, Optional
from pydantic import BaseModel


class Candidate(BaseModel):
    technician_id: str
    scheduled_start: str
    scheduled_end: str
    workload_before: int
    workload_after: int
    projected_workload_ratio: float


class AssignmentResult(BaseModel):
    assignment_id: str
    request_id: str
    technician_id: Optional[str] = None
    scheduled_start: Optional[str] = None
    scheduled_end: Optional[str] = None
    decision_status: str
    workload_before: Optional[int] = None
    workload_after: Optional[int] = None
    recommendation_reason: Dict
    created_at: str
