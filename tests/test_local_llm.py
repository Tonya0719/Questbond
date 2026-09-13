from src.llm.local_client import LocalOpenAICompatibleClient


def test_local_client_converts_tool_call_to_shared_format():
    captured = {}

    def fake_request(url, payload, api_key, timeout):
        captured.update({"url": url, "payload": payload, "api_key": api_key, "timeout": timeout})
        return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [{
            "id": "call-1", "type": "function", "function": {
                "name": "get_request_status", "arguments": '{"request_id":"R001"}'}}]}}],
            "usage": {"total_tokens": 12}}

    client = LocalOpenAICompatibleClient(base_url="http://localhost:1234/v1", model="local-model",
                                          api_key="test", request_func=fake_request)
    response = client.converse([{"role": "user", "content": [{"text": "schedule R001"}]}],
        "system", [{"toolSpec": {"name": "get_request_status", "description": "status",
                                   "inputSchema": {"json": {"type": "object"}}}}])
    tool_use = response["output"]["message"]["content"][0]["toolUse"]
    assert captured["url"] == "http://localhost:1234/v1/chat/completions"
    assert captured["payload"]["tools"][0]["function"]["name"] == "get_request_status"
    assert tool_use == {"toolUseId": "call-1", "name": "get_request_status", "input": {"request_id": "R001"}}


def test_local_client_converts_tool_result_for_next_turn():
    captured = {}

    def fake_request(url, payload, api_key, timeout):
        captured["messages"] = payload["messages"]
        return {"choices": [{"message": {"role": "assistant", "content": "Done"}}]}

    client = LocalOpenAICompatibleClient(model="local-model", request_func=fake_request)
    messages = [
        {"role": "assistant", "content": [{"toolUse": {
            "toolUseId": "call-1", "name": "get_request_status", "input": {"request_id": "R001"}}}]},
        {"role": "user", "content": [{"toolResult": {
            "toolUseId": "call-1", "status": "success", "content": [{"json": {"ready": True}}]}}]},
    ]
    response = client.converse(messages, "system", [])
    assert captured["messages"][-1] == {"role": "tool", "tool_call_id": "call-1",
                                        "content": '{"ready": true}'}
    assert response["output"]["message"]["content"] == [{"text": "Done"}]
