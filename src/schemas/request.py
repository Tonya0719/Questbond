from __future__ import annotations

from typing import List, Literal, Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator


class IntakeExtraction(BaseModel):
    service_rule_id: Optional[str] = None
    zone: Optional[Literal["North", "South", "East", "West", "Central"]] = None
    urgency: Literal["NORMAL", "URGENT"] = "NORMAL"
    window_start: Optional[str] = None
    window_end: Optional[str] = None


class StructuredRequest(BaseModel):
    request_id: str
    customer_id: Optional[str] = None
    service_rule_id: Optional[str] = None
    category: Optional[str] = None
    subtype: Optional[str] = None
    zone: Optional[Literal["North", "South", "East", "West", "Central"]] = None
    urgency: Literal["NORMAL", "URGENT"] = "NORMAL"
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    estimated_duration_min: Optional[int] = None
    missing_fields: List[str] = Field(default_factory=list)
    ready_for_scheduling: bool = False

    @field_validator("window_start", "window_end")
    @classmethod
    def validate_local_datetime(cls, value):
        if not value:
            return None
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is not None:
            raise ValueError("Use Singapore local datetimes without timezone offsets.")
        return parsed.isoformat(timespec="minutes")

    @model_validator(mode="after")
    def derive_readiness(self):
        if self.window_start and self.window_end:
            if self.window_start >= self.window_end:
                raise ValueError("The appointment window must end after it starts.")
            if self.window_start[:10] != self.window_end[:10]:
                raise ValueError("Use one appointment day per request.")
        required = ("service_rule_id", "zone", "window_start", "window_end", "estimated_duration_min")
        self.missing_fields = [field for field in required if getattr(self, field) in (None, "")]
        self.ready_for_scheduling = not self.missing_fields
        return self
