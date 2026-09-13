from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class AgentHandoff(BaseModel):
    handoff_id: str
    session_id: str
    source_agent: str
    target_agent: str
    handoff_type: str
    request_id: Optional[str] = None
    assignment_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
