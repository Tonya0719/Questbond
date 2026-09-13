from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..config import settings


class BedrockConverseClient:
    """Thin Amazon Bedrock Converse adapter with no scheduling business logic."""

    def __init__(self, model_id: Optional[str] = None, region: Optional[str] = None, client=None):
        self.model_id = model_id or settings.bedrock_model_id
        self.region = region or settings.aws_region
        if not self.model_id:
            raise ValueError("BEDROCK_MODEL_ID is required for the Bedrock backend")
        if client is None:
            import boto3
            client = boto3.client("bedrock-runtime", region_name=self.region)
        self.client = client

    def converse(self, messages: List[Dict[str, Any]], system_prompt: str,
                 tools: List[Dict[str, Any]], guardrail_config: Optional[dict] = None) -> dict:
        request = {"modelId": self.model_id, "messages": messages,
                   "system": [{"text": system_prompt}], "inferenceConfig": {"temperature": 0, "maxTokens": 800}}
        if tools:
            request["toolConfig"] = {"tools": tools}
        if guardrail_config:
            request["guardrailConfig"] = guardrail_config
        return self.client.converse(**request)


def run_tool_loop(client, executor, session_id: str, agent_name: str, messages: list,
                  system_prompt: str, tool_specs: list, max_tool_turns: int = 8) -> tuple[str, list]:
    transcript = list(messages)
    for _ in range(max_tool_turns):
        response = client.converse(transcript, system_prompt, tool_specs)
        output = response["output"]["message"]
        transcript.append(output)
        tool_uses = [block["toolUse"] for block in output.get("content", []) if "toolUse" in block]
        if not tool_uses:
            text = "\n".join(block.get("text", "") for block in output.get("content", []) if block.get("text"))
            return text, transcript
        results = []
        for call in tool_uses:
            try:
                value = executor.execute(session_id, agent_name, call["name"], call.get("input", {}))
                result = {"toolUseId": call["toolUseId"], "content": [{"json": value}], "status": "success"}
            except Exception as exc:
                result = {"toolUseId": call["toolUseId"], "content": [{"text": str(exc)}], "status": "error"}
            results.append({"toolResult": result})
        transcript.append({"role": "user", "content": results})
    raise RuntimeError(f"Agent exceeded maximum tool turns ({max_tool_turns})")
