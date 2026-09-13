from __future__ import annotations

import json
from pydantic import ValidationError

from ..schemas.request import IntakeExtraction


class IntakeParsingError(ValueError):
    pass


def parse_extraction(payload: str | dict) -> IntakeExtraction:
    try:
        data = json.loads(payload) if isinstance(payload, str) else payload
        return IntakeExtraction.model_validate(data)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise IntakeParsingError("Intake backend returned invalid structured JSON") from exc
