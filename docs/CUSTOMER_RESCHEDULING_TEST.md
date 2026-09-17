# Unavailable window followed by another request

Automated scenario: Alex is the only available technician qualified for the aircon diagnosis, and his shift starts at 14:00. The resident requests 15 January 2030, 10:00–13:00.

Expected conversation:

Resident: Aircon not cooling.

Assistant: No technician is free in that window. Could you choose another date or time?

Resident: Please check 15 January, 14:00–17:00.

Assistant: We’ve proposed Alex for 15 January 2030, 02:00 PM–03:30 PM. Your coordinator will confirm the visit.

The customer chooses the new window using **Another date**, **From**, **Until**, and **Check this time**. This is a customer-selected window, not an invented alternative. Every attempt checks current availability. It keeps the same request and a new agent session, preserving both decision traces. No booking is written until coordinator confirmation. Confirmed appointments require coordinator changes.

The customer sees only their conversation and readable service/time details. Internal messages, losing candidates, ranking, workload, tool activity, and IDs stay in the coordinator audit. Older conversations use an outcome-based fallback to avoid exposing their historical debug text.

Run from the repository with the mock backend:

```sh
LLM_BACKEND=mock python -m pytest tests/test_customer_conversation.py -q
```

The test uses an isolated database and does not change the running app’s technicians or charge the API.
