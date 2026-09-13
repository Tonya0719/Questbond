from __future__ import annotations

import json

from ..config import settings
from .parser import IntakeParsingError, parse_extraction


class BedrockClient:
    def __init__(self, model_id: str | None = None, region: str | None = None):
        self.model_id = model_id or settings.bedrock_model_id
        self.region = region or settings.aws_region
        if not self.model_id:
            raise ValueError("BEDROCK_MODEL_ID is required for the Bedrock backend")

    def extract_request(self, raw_message: str) -> dict:
        import boto3
        client = boto3.client("bedrock-runtime", region_name=self.region)
        prompt = ("Extract only service_rule_id, zone, urgency, window_start, and window_end. "
                  "Use null when unknown. Return one JSON object and do not invent service requirements. Request: " + raw_message)
        body = {"messages": [{"role": "user", "content": [{"text": prompt}]}],
                "inferenceConfig": {"temperature": 0, "maxTokens": 500}}
        last_error = None
        for _ in range(2):
            try:
                response = client.invoke_model(modelId=self.model_id, body=json.dumps(body))
                decoded = json.loads(response["body"].read())
                text = decoded.get("output", {}).get("message", {}).get("content", [{}])[0].get("text", "")
                return parse_extraction(text).model_dump()
            except (KeyError, json.JSONDecodeError, IntakeParsingError) as exc:
                last_error = exc
        raise IntakeParsingError("Bedrock did not return valid structured JSON after one retry") from last_error
