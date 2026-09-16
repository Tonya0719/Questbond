from __future__ import annotations

from typing import Any, Dict, List, Optional
from time import perf_counter

from .usage import record_model_call

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
    tool_count = 0
    for _ in range(max_tool_turns):
        started = perf_counter()
        try:
            response = client.converse(transcript, system_prompt, tool_specs)
        except Exception:
            record_model_call(executor.connection, session_id, agent_name, client, {},
                              int((perf_counter() - started) * 1000), "ERROR")
            raise
        record_model_call(executor.connection, session_id, agent_name, client, response,
                          int((perf_counter() - started) * 1000))
        output = response["output"]["message"]
        transcript.append(output)
        tool_uses = [block["toolUse"] for block in output.get("content", []) if "toolUse" in block]
        if not tool_uses:
            text = "\n".join(block.get("text", "") for block in output.get("content", []) if block.get("text"))
            return text, transcript
        results = []
        for call in tool_uses:
            tool_count += 1
            if tool_count > 16:
                raise RuntimeError("Agent exceeded the maximum tool calls (16); coordinator review required.")
            try:
                value = executor.execute(session_id, agent_name, call["name"], call.get("input", {}))
                result = {"toolUseId": call["toolUseId"], "content": [{"json": value}], "status": "success"}
            except Exception as exc:
                raise RuntimeError(f"Tool '{call['name']}' failed: {exc}. No booking was committed.") from exc
            results.append({"toolResult": result})
        transcript.append({"role": "user", "content": results})
    raise RuntimeError(f"Agent exceeded maximum tool turns ({max_tool_turns})")
