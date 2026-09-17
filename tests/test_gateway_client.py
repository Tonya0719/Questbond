from dataclasses import replace
import pytest
from src.llm import gateway_client as module


@pytest.mark.parametrize('base', ['https://api.softwaresystems.app', 'https://api.softwaresystems.app/v1'])
def test_gateway_tool_call_conversion(monkeypatch, base):
    monkeypatch.setattr(module, 'settings', replace(module.settings, llm_gateway_url=base,
        llm_gateway_api_key='test-only', llm_model='test-model'))
    def request(url, payload, key, timeout):
        assert url == 'https://api.softwaresystems.app/v1/chat/completions'
        assert key == 'test-only' and payload['model'] == 'test-model'
        return {'choices': [{'message': {'tool_calls': [{'id': 'demo', 'function': {'name': 'lookup', 'arguments': '{"id":"A"}'}}]}}], 'usage': {'prompt_tokens': 3}}
    result = module.GatewayClient(request_func=request).converse([], 'Demo', [])
    assert result['output']['message']['content'][0]['toolUse']['input'] == {'id': 'A'}
    assert result['usage']['prompt_tokens'] == 3


def test_gateway_does_not_send_credentials_over_http(monkeypatch):
    monkeypatch.setattr(module, 'settings', replace(module.settings, llm_gateway_url='http://example.com'))
    with pytest.raises(ValueError, match='HTTPS'):
        module.GatewayClient()
