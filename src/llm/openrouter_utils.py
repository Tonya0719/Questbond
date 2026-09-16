from __future__ import annotations

import json
import ssl
import certifi
from typing import Any, Callable, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OpenRouterCreditError(RuntimeError):
    """Raised when OpenRouter key/credit metadata cannot be retrieved."""


def check_openrouter_credit(
    api_key: str,
    timeout_sec: int = 20,
    request_func: Optional[Callable[[Request, int], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Return OpenRouter API-key usage metadata from ``/api/v1/key``.

    This helper is intentionally separate from the shared local LLM client so
    the normal OpenAI-compatible execution path remains vendor-neutral.
    It is meant for local development/debugging only and is never called by the
    agent runtime unless a developer invokes it explicitly.
    """
    if not api_key or api_key == "local":
        raise OpenRouterCreditError("A real OpenRouter API key is required for credit checking")

    request = Request(
        "https://openrouter.ai/api/v1/key",
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )

    try:
        if request_func is not None:
            payload = request_func(request, timeout_sec)
        else:
            with urlopen(request, timeout=timeout_sec, context=ssl.create_default_context(cafile=certifi.where())) as response:
                payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OpenRouterCreditError(f"OpenRouter HTTP {exc.code}: {detail[:500]}") from exc
    except URLError as exc:
        raise OpenRouterCreditError(f"Cannot connect to OpenRouter: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise OpenRouterCreditError("OpenRouter credit response was not valid JSON") from exc

    try:
        data = payload["data"]
    except (KeyError, TypeError) as exc:
        raise OpenRouterCreditError("OpenRouter credit response did not contain a data object") from exc

    if not isinstance(data, dict):
        raise OpenRouterCreditError("OpenRouter credit response data was not an object")
    return data


def format_openrouter_credit(data: Dict[str, Any]) -> str:
    """Format OpenRouter key metadata into a short developer-facing summary."""
    usage = data.get("usage")
    limit = data.get("limit")

    lines = []
    if isinstance(usage, (int, float)):
        if isinstance(limit, (int, float)):
            remaining = limit - usage
            lines.append(f"spent ${usage:.4f} of ${limit:.2f} -> ${remaining:.4f} remaining")
        else:
            lines.append(f"spent so far: ${usage:.4f} (no cap set on this key)")
    else:
        lines.append("usage information unavailable")

    rate_limit = data.get("rate_limit") or {}
    if isinstance(rate_limit, dict) and rate_limit:
        requests = rate_limit.get("requests")
        interval = rate_limit.get("interval")
        if requests is not None or interval is not None:
            lines.append(f"rate limit: {requests} requests per {interval}")

    return "\n".join(lines)
