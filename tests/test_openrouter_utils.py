import pytest

from src.llm.openrouter_utils import (
    OpenRouterCreditError,
    check_openrouter_credit,
    format_openrouter_credit,
)


def test_openrouter_credit_uses_key_endpoint_and_returns_data():
    captured = {}

    def fake_request(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.headers.get("Authorization")
        captured["timeout"] = timeout
        return {
            "data": {
                "usage": 1.25,
                "limit": 10.0,
                "rate_limit": {"requests": 20, "interval": "10s"},
            }
        }

    data = check_openrouter_credit("test-key", timeout_sec=7, request_func=fake_request)

    assert captured == {
        "url": "https://openrouter.ai/api/v1/key",
        "authorization": "Bearer test-key",
        "timeout": 7,
    }
    assert data["usage"] == 1.25
    assert "8.7500 remaining" in format_openrouter_credit(data)


def test_openrouter_credit_rejects_placeholder_key():
    with pytest.raises(OpenRouterCreditError):
        check_openrouter_credit("local")
