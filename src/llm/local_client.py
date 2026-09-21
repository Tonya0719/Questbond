from __future__ import annotations

import json
import ssl
import certifi
from typing import Any, Callable, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..config import settings


class LocalLLMError(RuntimeError):
    pass


class LocalOpenAICompatibleClient:
    """Adapter for local OpenAI-compatible chat-completions servers.

    It accepts and returns the Bedrock-shaped messages used by the shared agent
    tool loop, keeping local and Bedrock execution paths interchangeable.
    """

    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None,
                 api_key: Optional[str] = None, timeout_sec: Optional[int] = None,
                 request_func: Optional[Callable[..., dict]] = None):
        self.base_url = (base_url or settings.local_llm_base_url).rstrip("/")
        self.model = model or settings.local_llm_model
        self.api_key = api_key if api_key is not None else settings.local_llm_api_key
        self.timeout_sec = timeout_sec or settings.local_llm_timeout_sec
        self.request_func = request_func or self._http_request
        if not self.model:
            raise ValueError("LOCAL_LLM_MODEL is required when LLM_BACKEND=local")

    def converse(self, messages: List[Dict[str, Any]], system_prompt: str,
                 tools: List[Dict[str, Any]], guardrail_config: Optional[dict] = None) -> dict:
        payload = {"model": self.model, "messages": [{"role": "system", "content": system_prompt}],
                   "temperature": 0, "max_tokens": 800}
        payload["messages"].extend(self._to_openai_messages(messages))
        if tools:
            payload["tools"] = [self._to_openai_tool(item) for item in tools]
            payload["tool_choice"] = "auto"
        response = self.request_func(f"{self.base_url}/chat/completions", payload,
                                     self.api_key, self.timeout_sec)
        try:
            message = response["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LocalLLMError("Local LLM returned an invalid chat-completions response") from exc
        content = []
        if message.get("content"):
            content.append({"text": message["content"]})
        for call in message.get("tool_calls") or []:
            try:
                arguments = call["function"].get("arguments") or "{}"
                arguments = json.loads(arguments) if isinstance(arguments, str) else arguments
                content.append({"toolUse": {"toolUseId": call["id"],
                    "name": call["function"]["name"], "input": arguments}})
            except (KeyError, json.JSONDecodeError, TypeError) as exc:
                raise LocalLLMError("Local LLM returned an invalid tool call") from exc
        return {"output": {"message": {"role": "assistant", "content": content}},
                "id": response.get("id"),
                "stopReason": "tool_use" if message.get("tool_calls") else "end_turn",
                "usage": response.get("usage", {})}

    @staticmethod
    def _to_openai_tool(tool: dict) -> dict:
        spec = tool["toolSpec"]
        return {"type": "function", "function": {"name": spec["name"],
                "description": spec["description"], "parameters": spec["inputSchema"]["json"]}}

    @staticmethod
    def _to_openai_messages(messages: List[Dict[str, Any]]) -> list:
        converted = []
        for message in messages:
            role, blocks = message["role"], message.get("content", [])
            texts = [block["text"] for block in blocks if "text" in block]
            images = [block["image"] for block in blocks if "image" in block]
            tool_uses = [block["toolUse"] for block in blocks if "toolUse" in block]
            if role == "assistant" and tool_uses:
                converted.append({"role": "assistant", "content": "\n".join(texts) or None,
                    "tool_calls": [{"id": call["toolUseId"], "type": "function",
                        "function": {"name": call["name"], "arguments": json.dumps(call.get("input", {}))}}
                        for call in tool_uses]})
                continue
            tool_results = [block["toolResult"] for block in blocks if "toolResult" in block]
            if tool_results:
                for result in tool_results:
                    body = result.get("content", [{}])[0]
                    value = body.get("json", body.get("text", ""))
                    converted.append({"role": "tool", "tool_call_id": result["toolUseId"],
                                      "content": json.dumps(value) if not isinstance(value, str) else value})
                continue
            if images:
                content = [{"type": "text", "text": value} for value in texts]
                for item in images:
                    content.append({"type": "image_url", "image_url": {
                        "url": f"data:{item['media_type']};base64,{item['data']}", "detail": "high"}})
                converted.append({"role": role, "content": content})
            else:
                converted.append({"role": role, "content": "\n".join(texts)})
        return converted

    @staticmethod
    def _http_request(url: str, payload: dict, api_key: str, timeout_sec: int) -> dict:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        try:
            with urlopen(request, timeout=timeout_sec, context=ssl.create_default_context(cafile=certifi.where())) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            hint = {401: "Check the API key.", 402: "Check your credit balance.",
                    429: "Rate limit reached; try later.", 400: "Check model and tool compatibility."}.get(exc.code, "Provider request failed.")
            raise LocalLLMError(f"Model API HTTP {exc.code}. {hint}") from exc
        except URLError as exc:
            raise LocalLLMError(f"Cannot connect to local LLM at {url}: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise LocalLLMError("Local LLM response was not valid JSON") from exc
