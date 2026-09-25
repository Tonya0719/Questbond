# Manual UI Test — Agent Clarification When the Description Is Unclear

Focus: when the customer's description is **vague, ambiguous, or unsupported**,
the Intake Agent should ask back a **specific, example-bearing** clarification
question instead of guessing. Test this as a customer in the browser. All test
inputs are in English.

## Setup (important)

Both backends now refuse to guess an ambiguous service, so you can test either way:

**Option A — mock (free, deterministic; recommended for functional checks)**
```powershell
conda activate hackathon
$env:LLM_BACKEND="mock"
python -m streamlit run app.py
```
The follow-up wording is a fixed template, but the *decision* (clarify vs schedule)
is the real behaviour and is covered by `tests/test_intake_clarification.py`.

**Option B — gateway (paid; use to judge the model's phrasing)**
```powershell
conda activate hackathon
$env:LLM_BACKEND="gateway"; $env:LLM_MODEL="global.anthropic.claude-sonnet-4-5-20250929-v1:0"
python -m streamlit run app.py
```

Tip: start from a clean database so earlier test requests do not confuse the
coordinator queue — `python scripts/reset_db.py` (this deletes runtime records).

- Customer view needs no sign-in.
- Type the description in "What needs fixing?", keep the other fields filled with
  valid values (area + a valid future time window) UNLESS the case says otherwise,
  so that the ONLY thing forcing a follow-up is the unclear description.
- For each case record: Input -> Agent's follow-up question -> Pass/Fail.

---

## Case 1 — Completely vague problem
- Description: `I have a problem at home`
- Area: East. Time: valid future window.
- Expected: the agent asks **what needs fixing** and lists **concrete examples**
  (e.g. aircon leaking / pipe leaking / toilet blocked / socket repair). It must
  not pick a service type on its own and must not schedule.

## Case 2 — Vague "broken" with no trade
- Description: `Something is broken and I need help`
- Area: West. Time: valid future window.
- Expected: asks which repair is needed, with examples. No invented category.

## Case 3 — Ambiguous between two trades
- Description: `There is water on my floor`  (could be plumbing OR aircon leak)
- Area: Central. Time: valid future window.
- Expected: the agent does not guess one; it asks a clarifying question that
  distinguishes the likely causes (e.g. "is it from a pipe/tap, or from the
  air-conditioner?") with examples.

## Case 4 — Symptom without the actual fault
- Description: `My room is too hot`  (aircon not cooling? or something else)
- Area: North. Time: valid future window.
- Expected: asks what specifically needs attention rather than assuming a service;
  offers examples so the customer can confirm the real issue.

## Case 5 — Unsupported request
- Description: `Please fix my spaceship engine`
- Area: any. Time: valid future window.
- Expected: does not invent a supported service; asks what maintenance issue is
  needed (or routes to human review). It must not schedule a technician.

---

## What "pass" means

- The follow-up is **specific to the missing/unclear item**, gives at least one
  **concrete example**, and is **answerable in one short reply**.
- The agent **does not guess** a service type from an ambiguous description.
- No scheduling happens while the request is still unclear.
- The customer view shows only readable text — no internal candidates, workload,
  real technician names, or IDs.

## Follow-up round (optional but recommended)

After the agent asks its question, reply with a clear answer in the chat, e.g.:
- Case 1 -> `The aircon is leaking`
- Case 3 -> `It is dripping from the air-conditioner`
- Case 4 -> `The aircon runs but does not cool`

Expected: once the description becomes clear (and area + time are present), the
agent proceeds to a recommendation without asking the same thing again.

## Quick input reference (copy-paste)

| Case | Description text | Area | Time window |
|---|---|---|---|
| 1 | `I have a problem at home` | East | valid future window |
| 2 | `Something is broken and I need help` | West | valid future window |
| 3 | `There is water on my floor` | Central | valid future window |
| 4 | `My room is too hot` | North | valid future window |
| 5 | `Please fix my spaceship engine` | any | valid future window |

If any follow-up question is too generic or the agent guesses a service, capture
the exact `Input + Agent reply` and share it so the intake prompt can be tuned.
