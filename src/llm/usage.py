from datetime import datetime, timezone
import math
from uuid import uuid4


def record_model_call(connection, session_id, agent_name, client, response, duration_ms, status="SUCCESS"):
    usage = response.get("usage", {}) or {}
    cost = usage.get("cost")
    if not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0:
        cost = None
    connection.execute("INSERT INTO agent_model_calls VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
        f"MC-{uuid4().hex[:12]}", session_id, agent_name,
        getattr(client, "model", getattr(client, "model_id", None)), response.get("id"),
        usage.get("prompt_tokens", usage.get("inputTokens")),
        usage.get("completion_tokens", usage.get("outputTokens")), cost, status, duration_ms,
        datetime.now(timezone.utc).isoformat()))
    connection.commit()


def request_usage(connection, request_id):
    row = connection.execute("""SELECT COUNT(*) AS model_calls, COUNT(mc.cost_usd) AS priced_calls,
        SUM(mc.cost_usd) AS cost_usd, SUM(mc.input_tokens) AS input_tokens, SUM(mc.output_tokens) AS output_tokens
        FROM agent_model_calls mc JOIN agent_sessions s ON s.session_id=mc.session_id WHERE s.request_id=?""",
        (request_id,)).fetchone()
    return dict(row)
