# Review of the suggested spec

The attached specification is a design reference. The implementation retains Questbond's existing canonical service rules, two agents, validated handoffs and human-owned confirmation.

## Applied improvements

- Expanded separate prompts with explicit tool order, session ownership, relative-date context, missing-field handling, multilingual fallback, injection boundaries and grounded explanations.
- Unknown service categories are not invented. Only configured service rules can be scheduled.
- Vague times cannot silently become exact timestamps unless an explicit form window or customer clarification supplies evidence. Time windows are validated as local, ordered, single-day datetimes.
- Potential flooding, electrical sparking and gas hazards are flagged independently of LLM urgency. Multiple service categories are preserved in the original message and routed for coordinator review instead of silently dropping an issue.
- Each form carries an idempotency key. Reusing it with identical details returns the original request/session without running the agents again. Reusing it with different details is rejected. Different intentional requests require new keys.
- Repeated recommendation-tool calls in one session reuse the stored result. Current-session audit records identify the recommendation; the agent cannot accidentally use another session's older recommendation.
- Coordinator confirmation remains outside the model's tools. It revalidates eligibility and current conflicts under `BEGIN IMMEDIATE`, then writes the job, schedule and confirmation atomically. Repeated confirmation returns the existing work order.
- Tool failure stops the loop and is audited. Each agent is bounded to eight model turns and sixteen model-requested tool calls. Model errors are recorded; remote HTTP bodies and authorization headers are not displayed.
- Dashboard order: original request, extracted fields, candidate dispositions, decision/explanation, tool trace. Explanations use stored decision facts and human-readable exclusion reasons.
- Every live model response is logged with generation ID, token counts, latency and provider-reported cost when supplied. The dashboard sums costs per request across both agents and clarification turns. Missing costs are shown as unavailable/partial, never zero. Earlier uninstrumented runs cannot be reconstructed here.

## Deliberate differences

1. **Intake may retrieve context.** Removing its tools would lose customer history and canonical service lookup. Its allowlist still prohibits scheduling operations.
2. **Python ranks technicians.** We do not ask the model to perform scheduling math or change the existing ranking policy to 'least idle gap'. The LLM coordinates tools; server code checks and ranks every candidate.
3. **Recommendations are not bookings.** The model cannot create or approve an appointment. A coordinator confirms it through the controlled service.
4. **No self-confidence gate.** A model's confidence score is not a calibrated guarantee. Schema validation, explicit missing fields and business constraints govern readiness.
5. **Do not broaden categories yet.** Appliance, carpentry and pest control require new company service rules, durations and qualified technicians; the model cannot invent those records.
6. **Mixed issues require review.** Selecting only the most urgent issue could hide the remaining work. This prototype preserves the message and asks the coordinator to separate it. Automatic multi-job splitting is future scope.
7. **A finite suite is not exhaustive.** Report measured cases and failures with the model/provider version. Mock tests establish workflow and domain correctness, not live language accuracy.

## Remaining boundaries

Staff authentication, email sending, travel-time buffers, disruption recovery, verified alternative-slot suggestions, full multilingual evaluations and automatic resolution of mixed issues remain future milestones. The current view switcher is a local demo, not authorization. Hazard detection is conservative keyword triage, not a safety diagnosis or a guarantee that all dangerous requests will be detected.

## Validation commands

```sh
LLM_BACKEND=mock python -m pytest tests -q
LLM_BACKEND=mock python evaluation/run_eval.py
python scripts/test_agent_connection.py
```

The last command makes paid live API calls using synthetic data in a disposable database. It prints provider-reported run cost when complete usage data is available. The offline commands explicitly override `.env` so they never use paid inference.
