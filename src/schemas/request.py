from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field, model_validator


class IntakeExtraction(BaseModel):
    service_rule_id: Optional[str] = None
    zone: Optional[str] = None
    urgency: str = "NORMAL"
    window_start: Optional[str] = None
    window_end: Optional[str] = None


class StructuredRequest(BaseModel):
    request_id: str
    customer_id: Optional[str] = None
    service_rule_id: Optional[str] = None
    category: Optional[str] = None
    subtype: Optional[str] = None
    zone: Optional[str] = None
    urgency: str = "NORMAL"
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    estimated_duration_min: Optional[int] = None
    missing_fields: List[str] = Field(default_factory=list)
    ready_for_scheduling: bool = False

    @model_validator(mode="after")
    def derive_readiness(self):
        required = ("service_rule_id", "zone", "window_start", "window_end", "estimated_duration_min")
        self.missing_fields = [field for field in required if getattr(self, field) in (None, "")]
        self.ready_for_scheduling = not self.missing_fields
        return self
